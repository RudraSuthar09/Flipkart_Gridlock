"""
config.py — Central configuration for the prediction_api.
All paths, weight constants, and hyperparameters live here.
Changing a number here propagates everywhere without touching logic.
"""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
# config.py lives at: prediction_api/app/config.py
# parents[0] = prediction_api/app/
# parents[1] = prediction_api/
# parents[2] = Flipkart_Gridlock/   ← project root
PROJECT_ROOT  = Path(__file__).resolve().parents[2]
API_ROOT      = Path(__file__).resolve().parents[1]       # prediction_api/
DATA_DIR      = PROJECT_ROOT / "data"
RAW_CSV       = DATA_DIR / "feature_engineered.csv"
PROCESSED_DIR = DATA_DIR / "processed"
PARQUET_PATH           = PROCESSED_DIR / "canonical_timeseries.parquet"
PARQUET_SEVERITY_PATH  = PROCESSED_DIR / "canonical_severity_timeseries.parquet"
MODELS_DIR             = API_ROOT / "models"
BASELINE_JSON          = MODELS_DIR / "baseline_config.json"
BASELINE_SEVERITY_JSON = MODELS_DIR / "baseline_config_severity.json"
LGBM_MODEL             = MODELS_DIR / "lightgbm_model.txt"
LGBM_SEVERITY_MODEL    = MODELS_DIR / "lightgbm_model_severity.txt"
PCU_WEIGHTS            = MODELS_DIR / "pcu_weights.json"
VEHICLE_TYPE_MAPPING   = MODELS_DIR / "vehicle_type_mapping.json"

# ── CORS ───────────────────────────────────────────────────────────────────
CORS_ORIGINS = [
    "http://localhost:9000",   # vanilla JS dev server
    "http://localhost:3000",   # CRA dev server (if used)
    "http://localhost:5173",   # Vite dev server (React frontend)
    "http://localhost:5174",   # Vite fallback port
    "http://127.0.0.1:9000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "https://frontend-grid-380107538485.us-central1.run.app", # Google Cloud Run Frontend
]

# ── Training split ─────────────────────────────────────────────────────────
MIN_HISTORY_DAYS = 21    # skip examples with < 3 weeks of history (cold start)
TEST_DAYS        = 14    # last N days of the dataset → test set
VAL_DAYS         = 7     # previous N days before test → validation (early-stop)

# ── Baseline weights (§8) ──────────────────────────────────────────────────
# recent_h1..h4: last 4 hours — decays by 0.6 per step
HOUR_WEIGHTS = [0.6**1, 0.6**2, 0.6**3, 0.6**4]   # [0.6, 0.36, 0.216, 0.1296]

# same_hour_d1..d4: same hour previous 4 days — decays by 0.5 per step
DAY_WEIGHTS  = [0.5**1, 0.5**2, 0.5**3, 0.5**4]   # [0.5, 0.25, 0.125, 0.0625]

# same_hour_wd_w1..w3: same weekday+hour previous 3 weeks — decays by 0.5
WEEK_WEIGHTS = [0.5**1, 0.5**2, 0.5**3]            # [0.5, 0.25, 0.125]

# Pre-compute normalisation denominator (avoids recomputing per call)
WEIGHT_SUM   = sum(HOUR_WEIGHTS) + sum(DAY_WEIGHTS) + sum(WEEK_WEIGHTS)

# ── LightGBM hyperparameters (§9) ─────────────────────────────────────────
LGBM_PARAMS = {
    # Poisson objective: correct for sparse non-negative count data.
    # Default L2 would try to minimise MSE which heavily penalises large-
    # count outliers and under-predicts low-count locations.
    "objective":             "poisson",
    "n_estimators":          300,
    "learning_rate":         0.05,
    "num_leaves":            15,
    "max_depth":             4,
    "min_child_samples":     5,     # sparse data → allow small leaves
    "subsample":             0.8,
    "early_stopping_rounds": 30,
    "verbose":               -1,
}

# Severity model: Tweedie objective handles continuous zero-inflated target
# (severity_score is weighted-float, not integer count like violation_count).
# power=1.5 sits between Poisson (1) and Gamma (2) — typical for mixed
# zero-inflated continuous data. Try power in [1.0, 2.0] if results are poor.
LGBM_SEVERITY_PARAMS = {
    "objective":             "tweedie",
    "tweedie_variance_power": 1.5,
    "n_estimators":          300,
    "learning_rate":         0.05,
    "num_leaves":            15,
    "max_depth":             4,
    "min_child_samples":     5,
    "subsample":             0.8,
    "early_stopping_rounds": 30,
    "verbose":               -1,
}

# ── Column lists ───────────────────────────────────────────────────────────
# Columns used for Part 1 (§2)
PART1_COLS = [
    "location_key", "hour_slot", "year", "month", "day", "hour",
    "weekday", "is_weekend", "latitude", "longitude",
    "area", "police_station", "violation_count",
]

# Part 2 severity: load severity_score alongside the standard columns
SEVERITY_PART1_COLS = [
    "location_key", "hour_slot", "year", "month", "day", "hour",
    "weekday", "is_weekend", "latitude", "longitude",
    "area", "police_station", "severity_score", "lane_count",
]

# One-hot columns (derived at runtime from the CSV header — 27 total in actual data)
VIOLATION_ONEHOT_PREFIX = "--"   # columns containing "--" are the one-hot columns

# ── Feature names (fixed order — §5) ──────────────────────────────────────
FEATURE_NAMES = [
    "recent_h1", "recent_h2", "recent_h3", "recent_h4",
    "same_hour_d1", "same_hour_d2", "same_hour_d3", "same_hour_d4",
    "same_hour_wd_w1", "same_hour_wd_w2", "same_hour_wd_w3",
]
CONTEXT_FEATURES = ["hour", "weekday", "is_weekend", "horizon"]   # LightGBM extras (§5)
ALL_LGBM_FEATURES = FEATURE_NAMES + CONTEXT_FEATURES
