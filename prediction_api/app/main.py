"""
main.py — FastAPI application entry point.

Startup sequence (runs ONCE, before any request is served):
  [Part 1 — count-based predictions]
  1. Load the dense violation-count panel parquet → build pivot matrix.
  2. Build the location master from the raw CSV (lat/lon/area/station).
  3. Load the trained LightGBM count model from disk.

  [Part 2 — severity-weighted predictions]
  4. Load the dense severity panel parquet → build severity pivot matrix.
  5. Build the severity location metadata (lat/lon + lane data + dominant types).
  6. Load the trained LightGBM severity (Tweedie) model from disk.

All objects stored in app.state — never re-created per request.

CORS: origins are configured in app/config.py (CORS_ORIGINS list).
      If you add a new frontend port, add it there — not here.

Run locally:
  cd prediction_api
  uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    CENTRALITY_CACHE,
    CORS_ORIGINS,
    DATASET_CSV,
    RAW_CSV,
    PARQUET_PATH,
    PARQUET_SEVERITY_PATH,
    LGBM_MODEL,
    LGBM_SEVERITY_MODEL,
    PCU_WEIGHTS,
    VEHICLE_TYPE_MAPPING,
    ROAD_CLASS_LOOKUP,
    DEFAULT_ROAD_WEIGHT,
)
from app.routers.analytics import router as analytics_router
from app.routers.predictions import router as predictions_router
from app.routers.traffic_severity import router as severity_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Helper — build severity location metadata
# ─────────────────────────────────────────────────────────────────

def _build_severity_location_meta(raw_csv: Path) -> pd.DataFrame:
    """
    Build a per-location metadata table for the severity page, including:
      - lat/lon/area/police_station (from the standard location master)
      - lane_count (mean lane count per location from feature_engineered.csv)
      - dominant_vehicle_cat (most common PCU category at this location)
      - dominant_violation (most common violation type at this location)

    The 'dominant' fields are computed from the feature_engineered.csv's
    pcu_weight column and the one-hot violation columns.  pcu_weight encodes
    the vehicle category at the bucket level; the highest-weighted one-hot
    column gives the most common violation type.
    """
    log.info("Building severity location metadata from %s ...", raw_csv)

    # Load vehicle mapping and PCU weights for reverse-lookup
    pcu_to_cat: dict[float, str] = {}
    if VEHICLE_TYPE_MAPPING.exists() and PCU_WEIGHTS.exists():
        with open(VEHICLE_TYPE_MAPPING) as f:
            vmap = json.load(f)
        with open(PCU_WEIGHTS) as f:
            pcu = json.load(f)
        # Build pcu_value → category name map
        pcu_to_cat = {v: k for k, v in pcu.items() if isinstance(v, (int, float))}

    raw = pd.read_csv(raw_csv, low_memory=False)

    # Drop bad location_key
    bad = (
        raw["location_key"].isna()
        | (raw["location_key"].astype(str).str.strip() == "")
        | (raw["location_key"].astype(str).str.strip() == "No Junction")
    )
    raw = raw[~bad].copy()

    # ── One-hot violation columns ──────────────────────────────────
    # They are named "VIOLATION TYPE--NNN" (double-dash separator)
    onehot_cols = [c for c in raw.columns if "--" in c]

    def _dominant_violation(group_df: pd.DataFrame) -> str:
        if not onehot_cols:
            return ""
        sums = group_df[onehot_cols].sum()
        best = sums.idxmax()
        # Strip the numeric suffix (e.g. "WRONG PARKING--112" → "WRONG PARKING")
        return best.split("--")[0].strip() if best else ""

    def _dominant_vehicle_cat(group_df: pd.DataFrame) -> str:
        """
        Infer vehicle category from mean pcu_weight using the closest PCU
        value in the pcu_to_cat lookup table.  Falls back to 'car' (1.0).
        """
        if "pcu_weight" not in group_df.columns or not pcu_to_cat:
            return "car"
        mean_pcu = group_df["pcu_weight"].mean()
        # Find the closest PCU key
        closest = min(pcu_to_cat, key=lambda v: abs(v - mean_pcu))
        return pcu_to_cat[closest]

    def _first_non_null(series: pd.Series):
        valid = series.dropna()
        return valid.iloc[0] if len(valid) else None

    def _mode_or_null(series: pd.Series):
        valid = series.dropna()
        return valid.mode().iloc[0] if len(valid) else None

    # Per-location aggregation
    groups = raw.groupby("location_key", sort=False)

    rows = []
    for loc_key, grp in groups:
        lat = _first_non_null(grp["latitude"])
        lon = _first_non_null(grp["longitude"])
        if lat is None or lon is None:
            continue

        lane = grp["lane_count"].mean() if "lane_count" in grp.columns else None

        rows.append({
            "location_key":         loc_key,
            "latitude":             float(lat),
            "longitude":            float(lon),
            "area":                 _first_non_null(grp["area"]),
            "police_station":       _mode_or_null(grp["police_station"]),
            "lane_count":           float(lane) if lane is not None and pd.notna(lane) else None,
            "dominant_vehicle_cat": _dominant_vehicle_cat(grp),
            "dominant_violation":   _dominant_violation(grp),
        })

    meta = pd.DataFrame(rows)
    log.info("Severity location metadata: %d locations", len(meta))
    return meta


# ─────────────────────────────────────────────────────────────────
# Lifespan — startup + (optional) shutdown
# ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Everything before `yield` runs at startup (once).
    Everything after `yield` runs at shutdown (once).
    """
    t0 = time.time()
    log.info("=" * 60)
    log.info("STARTUP — loading models and panels...")
    log.info("=" * 60)

    from app.services.data_pipeline import load_panel, load_and_validate, build_location_master
    from app.services.feature_engineering import build_pivot_matrix
    from app.services.model_lightgbm import LGBMPredictor

    # ══════════════════════════════════════════════════════════
    # Part 1 — Count-based models
    # ══════════════════════════════════════════════════════════

    # ── Load OSM road weights once — shared by both Part 1 and Part 2 ──
    road_weights: dict = {}
    if ROAD_CLASS_LOOKUP.exists():
        with open(ROAD_CLASS_LOOKUP, encoding="utf-8") as f:
            _lookup = json.load(f)
        road_weights = {k: v["road_weight"] for k, v in _lookup.items()}
        log.info("OSM road weights loaded: %d locations", len(road_weights))
    else:
        log.info("road_class_lookup.json not found — road_weight_osm defaults to %.2f", DEFAULT_ROAD_WEIGHT)
    app.state.road_weights = road_weights

    log.info("[Part 1] Loading count panel from %s ...", PARQUET_PATH)
    panel = load_panel(PARQUET_PATH)

    log.info("[Part 1] Building pivot matrix (%d rows)...", len(panel))
    t1 = time.time()
    pivot_data = build_pivot_matrix(panel)
    log.info("  Pivot ready in %.1fs  (%d locs × %d hours)",
             time.time() - t1,
             len(pivot_data.loc_to_pos),
             pivot_data.matrix.shape[0])
    del panel

    log.info("[Part 1] Loading location master from %s ...", RAW_CSV)
    raw_df = load_and_validate(RAW_CSV)
    location_master = build_location_master(raw_df)
    del raw_df

    log.info("[Part 1] Loading LightGBM count model from %s ...", LGBM_MODEL)
    lgbm = LGBMPredictor().load(LGBM_MODEL)

    app.state.pivot_data         = pivot_data
    app.state.location_master    = location_master
    app.state.lgbm               = lgbm
    app.state.panel_rows         = pivot_data.matrix.shape[0] * pivot_data.matrix.shape[1]
    app.state.panel_last_updated = str(pivot_data.panel_end)

    # ══════════════════════════════════════════════════════════
    # Part 2 — Severity-weighted models
    # ══════════════════════════════════════════════════════════

    if PARQUET_SEVERITY_PATH.exists():
        try:
            log.info("[Part 2] Loading severity panel from %s ...", PARQUET_SEVERITY_PATH)
            severity_panel = load_panel(PARQUET_SEVERITY_PATH)

            log.info("[Part 2] Building severity pivot matrix (%d rows)...", len(severity_panel))
            t2 = time.time()
            severity_pivot = build_pivot_matrix(severity_panel)
            log.info("  Severity pivot ready in %.1fs", time.time() - t2)
            del severity_panel

            log.info("[Part 2] Building severity location metadata...")
            severity_loc_meta = _build_severity_location_meta(RAW_CSV)

            app.state.severity_pivot_data          = severity_pivot
            app.state.severity_location_meta       = severity_loc_meta
            app.state.severity_panel_rows          = severity_pivot.matrix.shape[0] * severity_pivot.matrix.shape[1]
            app.state.severity_panel_last_updated  = str(severity_pivot.panel_end)

        except Exception as exc:
            log.warning("[Part 2] Severity panel load failed: %s", exc)
            app.state.severity_pivot_data    = None
            app.state.severity_location_meta = pd.DataFrame()
    else:
        log.warning(
            "[Part 2] Severity parquet not found at %s. "
            "Run: python scripts/build_canonical_timeseries.py --target severity",
            PARQUET_SEVERITY_PATH,
        )
        app.state.severity_pivot_data    = None
        app.state.severity_location_meta = pd.DataFrame()

    # ══════════════════════════════════════════════════════════
    # Part 3 — Analytics data (PIS, Dark Fleet, Station Stats)
    # ══════════════════════════════════════════════════════════
    try:
        from app.services.analytics_pipeline import (
            build_pis_and_profiles,
            build_dark_fleet_and_station_stats,
            build_persistence_scores,
        )

        log.info("[Part 3] Building PIS scores and hourly profiles...")
        pis_records, hourly_profiles = build_pis_and_profiles(RAW_CSV, CENTRALITY_CACHE)

        log.info("[Part 3] Building dark fleet and station stats...")
        dark_fleet, fleet_station_map, station_stats = build_dark_fleet_and_station_stats(DATASET_CSV)

        log.info("[Part 3] Computing persistence scores from pivot matrix...")
        persistence_scores = build_persistence_scores(pivot_data)

        app.state.pis_scores        = pis_records
        app.state.hourly_profiles   = hourly_profiles
        app.state.dark_fleet        = dark_fleet
        app.state.fleet_station_map = fleet_station_map
        app.state.station_stats     = station_stats
        app.state.persistence_scores = persistence_scores

        log.info(
            "[Part 3] Analytics ready: %d PIS records | %d dark fleet vehicles | "
            "%d stations | %d hourly profiles",
            len(pis_records),
            len(dark_fleet),
            len(station_stats),
            len(hourly_profiles),
        )
    except Exception as exc:
        log.warning("[Part 3] Analytics build failed (non-fatal): %s", exc)
        app.state.pis_scores         = []
        app.state.hourly_profiles    = {}
        app.state.dark_fleet         = []
        app.state.fleet_station_map  = {}
        app.state.station_stats      = []
        app.state.persistence_scores = {}

    # Load severity LightGBM model (Tweedie)
    if LGBM_SEVERITY_MODEL.exists():
        try:
            log.info("[Part 2] Loading LightGBM severity model from %s ...", LGBM_SEVERITY_MODEL)
            app.state.lgbm_severity = LGBMPredictor().load(LGBM_SEVERITY_MODEL)
        except Exception as exc:
            log.warning("[Part 2] Severity model load failed: %s", exc)
            app.state.lgbm_severity = None
    else:
        log.warning(
            "[Part 2] Severity model not found at %s. "
            "Run: python scripts/train_models.py --target severity",
            LGBM_SEVERITY_MODEL,
        )
        app.state.lgbm_severity = None

    log.info("=" * 60)
    log.info(
        "READY in %.1fs  |  %d locations  |  panel ends %s",
        time.time() - t0,
        len(location_master),
        pivot_data.panel_end,
    )
    if app.state.lgbm_severity is not None:
        log.info("  ✓ Severity model loaded")
    else:
        log.info("  ✗ Severity model NOT loaded (train first)")
    log.info("=" * 60)

    yield

    log.info("Shutdown complete.")


# ─────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Violation Prediction API",
    description = (
        "Predictive heatmap for Bengaluru traffic violations. "
        "Part 1: violation-count ranking (/api/v1/only-prediction). "
        "Part 2: severity-weighted ranking (/api/v1/traffic-severity). "
        "A truck blocking a 1-lane road outranks 5 scooters on a footpath."
    ),
    version     = "2.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = CORS_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["GET", "POST", "OPTIONS"],
    allow_headers     = ["*"],
)

# ── Routers ──────────────────────────────────────────────────────
app.include_router(predictions_router, prefix="/api/v1",                 tags=["predictions"])
app.include_router(severity_router,    prefix="/api/v1/traffic-severity", tags=["severity"])
app.include_router(analytics_router,   prefix="/api/v1",                  tags=["analytics"])


# ─────────────────────────────────────────────────────────────────
# Root redirect → docs
# ─────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")
