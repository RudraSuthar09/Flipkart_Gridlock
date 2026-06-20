# Flipkart Gridlock — Traffic Violation Prediction

Bengaluru traffic-violation heatmap with two complementary prediction engines:

| Page | Route | What it predicts | Model |
|---|---|---|---|
| **Count Heatmap** | `#/only-prediction` | Expected **violation count** | LightGBM (Poisson) |
| **Severity Heatmap** | `#/traffic-severity` | Expected **severity score** | LightGBM (Tweedie) |

> **Why two heatmaps?**  
> A truck blocking a 1-lane road has `severity = 3.0 × 1.0 × 1.0 = 3.0`.  
> Four scooters parked on a 4-lane footpath have `severity = 4 × (0.5 × 0.25 × 1.0) = 0.5`.  
> The count heatmap ranks the footpath #1 (4 > 1 violations). The severity heatmap correctly ranks the truck incident #1 (3.0 > 0.5). Part 2 exists to fix that.

---

## Project Structure

```
Flipkart_Gridlock/
├── data/
│   ├── feature_engineered.csv              # raw enriched dataset
│   └── processed/
│       ├── canonical_timeseries.parquet    # Part 1 count panel
│       └── canonical_severity_timeseries.parquet  # Part 2 severity panel
├── frontend/
│   ├── index.html
│   └── src/
│       ├── app.js                  # hash router
│       ├── only_prediction.js      # Part 1 heatmap (indigo theme)
│       ├── traffic_severity.js     # Part 2 heatmap (amber theme)
│       └── styles.css
└── prediction_api/
    ├── app/
    │   ├── main.py                 # FastAPI lifespan — loads both models
    │   ├── config.py               # all paths + hyperparameters
    │   ├── schemas.py              # Pydantic request/response models
    │   ├── routers/
    │   │   ├── predictions.py      # /api/v1/only-prediction/*
    │   │   └── traffic_severity.py # /api/v1/traffic-severity/*
    │   └── services/
    │       ├── data_pipeline.py    # load/aggregate/densify panel
    │       ├── feature_engineering.py  # 11-feature lookback builder
    │       ├── model_baseline.py   # recency-weighted baseline
    │       └── model_lightgbm.py   # LightGBM wrapper (Poisson + Tweedie)
    ├── scripts/
    │   ├── build_canonical_timeseries.py   # --target {count,severity}
    │   └── train_models.py                 # --target {count,severity}
    ├── models/
    │   ├── lightgbm_model.txt              # Part 1 Poisson model
    │   ├── lightgbm_model_severity.txt     # Part 2 Tweedie model
    │   ├── baseline_config.json
    │   ├── baseline_config_severity.json
    │   ├── pcu_weights.json                # PCU values per vehicle category
    │   └── vehicle_type_mapping.json       # 22 vehicle types → canonical categories
    ├── test_api.py                         # Part 1 integration smoke test
    └── test_severity.py                    # Part 2 unit + integration tests
```

---

## Severity Score Formula

```
severity_score (per violation row) = vehicle_weight × road_weight × violation_type_weight

where:
  vehicle_weight      = PCU value for vehicle category (two-wheeler=0.5, heavy truck=3.0)
  road_weight         = 1 / lane_count  (1-lane road = 1.0, 4-lane = 0.25)
  violation_type_weight = 1.0–2.0 depending on hazard class of the violation

Location bucket severity = SUM of per-row severities at that (location, hour)
```

PCU weights and vehicle mappings are in [`models/pcu_weights.json`](prediction_api/models/pcu_weights.json) and [`models/vehicle_type_mapping.json`](prediction_api/models/vehicle_type_mapping.json). Change numbers there to re-rank without retraining.

---

## Quick Start

### 1. Build panels + train models

```powershell
cd prediction_api

# Part 1 — violation count
python scripts/build_canonical_timeseries.py --target count
python scripts/train_models.py --target count

# Part 2 — severity score (requires lane_count + severity_score in feature_engineered.csv)
python scripts/build_canonical_timeseries.py --target severity
python scripts/train_models.py --target severity --zero-sample-rate 0.05
```

### 2. Start the API server

```powershell
cd prediction_api
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### 3. Serve the frontend

```powershell
cd frontend
python -m http.server 9000
# Then open http://localhost:9000
```

### 4. Run tests

```powershell
cd prediction_api

# Part 1 smoke test (requires running server)
python test_api.py

# Part 2 unit + integration tests
$env:PYTHONIOENCODING="utf-8"; python test_severity.py
```

---

## API Endpoints

### Part 1 — Count Heatmap  (`/api/v1/`)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Model load status, panel stats |
| GET | `/api/v1/locations` | All 6,333 location lat/lons |
| GET | `/api/v1/predict?timestamp=...&top_n=N` | Ranked violation-count predictions |

### Part 2 — Severity Heatmap  (`/api/v1/traffic-severity/`)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/traffic-severity/health` | Model status + coverage metrics |
| GET | `/api/v1/traffic-severity/locations` | Locations + lane data + dominant vehicle/violation |
| GET | `/api/v1/traffic-severity/predict?timestamp=...&top_n=N` | Ranked severity predictions with explainability |

Interactive docs: **http://127.0.0.1:8001/docs**

---

## Models

| Model | Objective | Target | Training label mean | Precision@5 |
|---|---|---|---|---|
| Baseline (Part 1) | Recency-weighted dot product | violation_count | — | ~0.19 |
| LightGBM (Part 1) | Poisson | violation_count | ~0.14 | ~0.19 |
| Baseline (Part 2) | Recency-weighted dot product | severity_score | — | ~0.19 |
| LightGBM (Part 2) | Tweedie (power=1.5) | severity_score | ~0.007 | ~0.19 |

Precision@5 is computed over the last 14 days of the dataset, averaging over all hourly timestamps. 99.6% of (location, hour) pairs have zero severity — the extreme sparsity means the baseline is hard to beat with a small training set, but the Tweedie model correctly predicts the *shape* of the risk distribution.

---

## Data Quality

The `/api/v1/traffic-severity/health` endpoint reports two coverage metrics:

- **`vehicle_mapping_coverage`** — fraction of vehicle type codes with a confirmed PCU mapping. Currently **1.0 (100%)** because the dataset uses readable text strings (not encoded integers) so all 22 types are matched.
- **`lane_match_coverage`** — fraction of locations where `lane_count` is a real non-zero value. Locations with `lane_count = 0` use the default road_weight of 0.5.

---

## Design Decisions

- **Tweedie vs Poisson for severity**: severity_score is a continuous float (not an integer count), so Poisson would be wrong. Tweedie with power=1.5 handles zero-inflated continuous data correctly.
- **`violation_count` column renamed in panel**: the dense panel always uses `violation_count` as the value column for downstream compatibility with `feature_engineering.py`. The build script renames `severity_score → violation_count` before saving.
- **LGBMPredictor accepts `lgbm_params`**: the single `LGBMPredictor` class handles both Poisson (Part 1) and Tweedie (Part 2) by accepting an optional `lgbm_params` dict in `__init__`. No separate class needed.
- **Graceful degradation**: if the severity panel or model is missing at startup, the API logs a warning and Part 1 still works normally.