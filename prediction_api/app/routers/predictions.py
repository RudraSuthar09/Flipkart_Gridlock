"""
predictions.py — FastAPI router with 3 endpoints.

Endpoints
---------
GET  /health        → API + model status (used by frontend on load)
GET  /locations     → Static list of all 6,333 locations with lat/lon
GET  /predict       → Ranked predictions for a given target timestamp

All heavy state (panel, pivot, location master, LightGBM) lives in
app.state, loaded ONCE at startup in main.py — not here.  This router
only reads from app.state; it never trains or reloads anything.

Design decision — GET for /predict (not POST):
  The predict request has no side effects and is fully parameterised by
  a single timestamp string.  GET is correct here, allows browser caching,
  and makes the URL shareable (e.g. bookmark a particular hour's forecast).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

from app.config import FEATURE_NAMES, ALL_LGBM_FEATURES, DEFAULT_ROAD_WEIGHT
from app.schemas import HealthResponse, LocationRecord, PredictionRecord
from app.services.feature_engineering import build_feature_matrix
from app.services.model_baseline import naive_predict, baseline_predict

log = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────
# /health
# ─────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """
    Return model-load status and panel statistics.
    The frontend calls this on page load to confirm the API is ready
    before rendering the prediction UI.
    """
    state = request.app.state
    return HealthResponse(
        status             = "ok",
        model_loaded       = getattr(state, "lgbm", None) is not None
                             and getattr(state, "lgbm").is_loaded,
        panel_rows         = getattr(state, "panel_rows",         0),
        panel_last_updated = str(getattr(state, "panel_last_updated", "unknown")),
        location_count     = len(getattr(state, "location_master", [])),
    )


# ─────────────────────────────────────────────────────────────────
# /locations
# ─────────────────────────────────────────────────────────────────

@router.get("/locations", response_model=List[LocationRecord])
async def get_locations(request: Request) -> List[LocationRecord]:
    """
    Return the static location master: one entry per junction / grid cell.

    Used by the frontend to render base markers on the map before any
    prediction timestamp is selected.  Response is cache-friendly (the
    location master never changes without a full server restart).
    """
    master: pd.DataFrame = request.app.state.location_master
    records = master.replace({np.nan: None}).to_dict("records")
    return [LocationRecord(**r) for r in records]


# ─────────────────────────────────────────────────────────────────
# /predict
# ─────────────────────────────────────────────────────────────────

@router.get("/predict", response_model=List[PredictionRecord])
async def predict(
    request:   Request,
    timestamp: str = Query(
        ...,
        description=(
            "Target timestamp in ISO-8601 format (e.g. '2024-03-26T14:00:00'). "
            "Minute/second components are ignored — predictions are hourly."
        ),
        examples=["2024-03-26T14:00:00"],
    ),
    top_n: Optional[int] = Query(
        None,
        ge=1,
        le=6333,
        description="Return only the top-N riskiest locations (default: all).",
    ),
    active_only: bool = Query(
        True,
        description="If true (default), only return locations with actual historical activity in the lookback window (at least one non-zero lookback feature). Set to false to return all locations.",
    ),
) -> List[PredictionRecord]:
    """
    Produce ranked violation-risk predictions for every location at the
    given target timestamp.

    Algorithm (per §5 + §8 + §9):
      1. Parse and floor timestamp to the nearest hour.
      2. Build the 11-feature lookback vector for every location at once
         (vectorised numpy — one call, not a Python loop).
      3. naive_prediction    = same_hour_d1 (feature index 4).
      4. baseline_prediction = recency-weighted dot product / weight_sum.
      5. lightgbm_prediction = LightGBM Poisson model on 14 features.
      6. Sort by lightgbm_prediction descending; assign integer rank (1 = riskiest).
      7. Return the ranked list (optionally truncated to top_n).

    Future timestamps (after the panel end) are handled gracefully:
    feature extraction returns 0 for any lookback that falls outside the
    panel range (cold-start rule), so predictions degrade to the model's
    learned prior — they do NOT raise an error.
    """
    # ── 1. Parse timestamp ────────────────────────────────────────
    try:
        target_ts = pd.Timestamp(timestamp).floor("h")
    except Exception:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot parse timestamp: '{timestamp}'. Use ISO-8601 format.",
        )

    state      = request.app.state
    pivot_data = state.pivot_data
    location_master: pd.DataFrame = state.location_master
    lgbm       = state.lgbm

    if not lgbm.is_loaded:
        raise HTTPException(
            status_code=503,
            detail="LightGBM model is not loaded. Check server logs.",
        )

    # ── 2. Build features for ALL locations at once ───────────────
    all_locs = list(pivot_data.loc_to_pos.keys())
    n        = len(all_locs)
    all_ts   = [target_ts] * n

    # Calculate horizon in hours
    panel_end = pivot_data.panel_end
    diff_h    = int((target_ts - panel_end).total_seconds() // 3600)
    horizon_h = max(0, diff_h)
    horizons_h = np.full(n, horizon_h, dtype=np.int64)

    feat_mat = build_feature_matrix(pivot_data, all_ts, all_locs, horizons_h)
    # feat_mat: shape (n, 11), dtype float32

    # ── Filter: keep only locations with actual historical data ───
    # A location has activity if ANY of its 11 lookback features is > 0.
    # Without this, LightGBM returns a small positive Poisson prior for
    # every location, flooding the map with meaningless dots.
    has_activity = feat_mat.any(axis=1)  # shape (n,), bool

    if active_only:
        active_mask = has_activity
        feat_mat_active = feat_mat[active_mask]
        all_locs_active = [loc for loc, a in zip(all_locs, active_mask) if a]
        horizons_h_active = horizons_h[active_mask]
    else:
        active_mask = np.ones(n, dtype=bool)
        feat_mat_active = feat_mat
        all_locs_active = all_locs
        horizons_h_active = horizons_h

    n_active = len(all_locs_active)
    log.info(
        "Predict TS=%s  total_locs=%d  active_locs=%d (active_only=%s)",
        target_ts, n, n_active, active_only,
    )

    if n_active == 0:
        return []

    # ── 3–4. Naive + Baseline (pure numpy) ───────────────────────
    naive_preds    = naive_predict(feat_mat_active)
    baseline_preds = baseline_predict(feat_mat_active)

    # ── 5. LightGBM (16 features: 11 lookback + hour/weekday/is_weekend/horizon/road_weight_osm)
    wd  = target_ts.weekday()
    iwe = int(wd >= 5)
    rw_dict = getattr(state, "road_weights", {})
    road_w  = np.array(
        [rw_dict.get(loc, DEFAULT_ROAD_WEIGHT) for loc in all_locs_active],
        dtype=np.float32,
    )
    ctx_cols = np.column_stack([
        np.full(n_active, target_ts.hour, dtype=np.float32),
        np.full(n_active, wd,             dtype=np.float32),
        np.full(n_active, iwe,            dtype=np.float32),
        np.full(n_active, horizon_h,      dtype=np.float32),
        road_w,
    ])                             # shape (n_active, 5)
    X_lgbm = np.hstack([feat_mat_active, ctx_cols])   # shape (n_active, 16)

    lgbm_raw  = lgbm.predict(X_lgbm)

    # Scale Poisson rate to a readable 0–100 risk index.
    # The model outputs expected violations/hr in the 0.001–0.02 range.
    # Multiplying by 1000 gives a 1–20 risk score while preserving ranking.
    LGBM_SCALE = 1000.0
    lgbm_preds = lgbm_raw * LGBM_SCALE

    # ── 6. Assemble result DataFrame + rank ──────────────────────
    result_df = pd.DataFrame({
        "location_key":           all_locs_active,
        "naive_prediction":       naive_preds.astype(float),
        "baseline_prediction":    baseline_preds.astype(float),
        "lightgbm_prediction":    lgbm_preds.astype(float),
    })

    # Join with location master for lat/lon/area/police_station
    merged = result_df.merge(location_master, on="location_key", how="left")

    # Drop unmappable locations (no lat/lon in master)
    merged = merged.dropna(subset=["latitude", "longitude"])

    # Sort descending by LightGBM score; assign 1-based rank
    merged = merged.sort_values("lightgbm_prediction", ascending=False).reset_index(drop=True)
    merged["rank_lightgbm"] = range(1, len(merged) + 1)

    # ── 7. Optional truncation ────────────────────────────────────
    if top_n is not None:
        merged = merged.head(top_n)

    log.info(
        "Predict TS=%s  active_locs=%d  returned=%d  max_lgbm=%.4f",
        target_ts, n_active, len(merged),
        merged["lightgbm_prediction"].iloc[0] if len(merged) else 0,
    )

    # ── 8. Serialise ─────────────────────────────────────────────
    merged = merged.replace({np.nan: None})
    records = merged.to_dict("records")
    return [PredictionRecord(**r) for r in records]
