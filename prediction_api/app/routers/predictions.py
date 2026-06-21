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

from app.config import FEATURE_NAMES, ALL_LGBM_FEATURES
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
        example="2024-03-26T14:00:00",
    ),
    top_n: Optional[int] = Query(
        None,
        ge=1,
        le=6333,
        description="Return only the top-N riskiest locations (default: all).",
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

    # ── 3–4. Naive + Baseline (pure numpy) ───────────────────────
    naive_preds    = naive_predict(feat_mat)
    baseline_preds = baseline_predict(feat_mat)

    # ── 5. LightGBM (15 features: 11 lookback + hour/weekday/is_weekend/horizon)
    wd  = target_ts.weekday()      # Timestamp.weekday() IS callable (not property)
    iwe = int(wd >= 5)
    ctx_cols = np.array(
        [[target_ts.hour, wd, iwe, horizon_h]] * n, dtype=np.float32
    )                              # shape (n, 4)
    X_lgbm = np.hstack([feat_mat, ctx_cols])   # shape (n, 15)

    lgbm_preds = lgbm.predict(X_lgbm)

    # ── 6. Assemble result DataFrame + rank ──────────────────────
    result_df = pd.DataFrame({
        "location_key":           all_locs,
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

    log.debug(
        "Predict TS=%s  locs=%d  max_lgbm=%.4f",
        target_ts, len(merged),
        merged["lightgbm_prediction"].iloc[0] if len(merged) else 0,
    )

    # ── 8. Serialise ─────────────────────────────────────────────
    merged = merged.replace({np.nan: None})
    records = merged.to_dict("records")
    return [PredictionRecord(**r) for r in records]
