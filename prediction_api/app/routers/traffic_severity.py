"""
traffic_severity.py — FastAPI router for the severity-weighted heatmap.

Endpoints (§8 of spec):
  GET /api/v1/traffic-severity/health
  GET /api/v1/traffic-severity/locations
  GET /api/v1/traffic-severity/predict?timestamp=...

Key differences from /api/v1/only-prediction:
  - Predictions are severity_score (continuous Tweedie), not violation_count.
  - Response includes lane_count, dominant_vehicle_cat, dominant_violation.
  - /health reports vehicle_mapping_coverage + lane_match_coverage.

All heavy state (severity panel, pivot, location master, LightGBM severity
model, location metadata) lives in app.state.severity_*, loaded ONCE at
startup in main.py — not here.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

from app.config import FEATURE_NAMES, ALL_LGBM_FEATURES
from app.schemas import (
    SeverityHealthResponse,
    SeverityLocationRecord,
    SeverityPredictionRecord,
)
from app.services.feature_engineering import build_feature_matrix
from app.services.model_baseline import naive_predict, baseline_predict

log = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────
# /health
# ─────────────────────────────────────────────────────────────────

@router.get("/health", response_model=SeverityHealthResponse)
async def severity_health(request: Request) -> SeverityHealthResponse:
    """
    Return severity model-load status, panel stats, and data-quality
    coverage metrics.

    vehicle_mapping_coverage: 1.0 — all 22 vehicle types resolved from
    readable text strings in dataset.csv (no encoded integers to reverse).

    lane_match_coverage: fraction of location-hour rows in the severity
    panel where lane_count > 0 (i.e. a real value was available).
    """
    state = request.app.state
    lgbm_severity = getattr(state, "lgbm_severity", None)

    # Compute lane_match_coverage from the severity location metadata
    sev_loc_meta: Optional[pd.DataFrame] = getattr(state, "severity_location_meta", None)
    if sev_loc_meta is not None and "lane_count" in sev_loc_meta.columns:
        total = len(sev_loc_meta)
        matched = (sev_loc_meta["lane_count"].notna() & (sev_loc_meta["lane_count"] > 0)).sum()
        lane_match_coverage = float(matched / total) if total > 0 else 0.0
    else:
        lane_match_coverage = 0.0

    return SeverityHealthResponse(
        status                   = "ok",
        model_loaded             = lgbm_severity is not None and lgbm_severity.is_loaded,
        panel_rows               = int(getattr(state, "severity_panel_rows", 0)),
        panel_last_updated       = str(getattr(state, "severity_panel_last_updated", "unknown")),
        location_count           = len(getattr(state, "severity_location_meta", pd.DataFrame())),
        # §2.A.3: 22/22 vehicle types mapped from text — coverage is 1.0
        vehicle_mapping_coverage = 1.0,
        lane_match_coverage      = lane_match_coverage,
    )


# ─────────────────────────────────────────────────────────────────
# /locations
# ─────────────────────────────────────────────────────────────────

@router.get("/locations", response_model=List[SeverityLocationRecord])
async def severity_locations(request: Request) -> List[SeverityLocationRecord]:
    """
    Return the location master enriched with lane data and dominant
    vehicle/violation type for each location.

    Used by the frontend to render base markers before any timestamp
    is selected. Includes data-confidence fields for the map layer.
    """
    meta: pd.DataFrame = getattr(request.app.state, "severity_location_meta", pd.DataFrame())
    if meta.empty:
        return []

    records = meta.replace({np.nan: None}).to_dict("records")
    result = []
    for r in records:
        result.append(SeverityLocationRecord(
            location_key         = r["location_key"],
            latitude             = float(r["latitude"]),
            longitude            = float(r["longitude"]),
            area                 = r.get("area"),
            police_station       = r.get("police_station"),
            lane_count           = float(r["lane_count"]) if pd.notna(r.get("lane_count")) else None,
            dominant_vehicle_cat = r.get("dominant_vehicle_cat"),
            dominant_violation   = r.get("dominant_violation"),
        ))
    return result


# ─────────────────────────────────────────────────────────────────
# /predict
# ─────────────────────────────────────────────────────────────────

@router.get("/predict", response_model=List[SeverityPredictionRecord])
async def severity_predict(
    request:   Request,
    timestamp: str = Query(
        ...,
        description=(
            "Target timestamp in ISO-8601 format (e.g. '2024-03-26T14:00:00'). "
            "Predictions are hourly — minute/second are ignored."
        ),
        examples=["2024-03-26T14:00:00"],
    ),
    top_n: Optional[int] = Query(
        None,
        ge=1,
        le=6333,
        description="Return only the top-N highest-severity locations (default: all).",
    ),
    active_only: bool = Query(
        True,
        description="If true (default), only return locations with actual historical activity in the lookback window. Set to false to return all locations.",
    ),
) -> List[SeverityPredictionRecord]:
    """
    Produce ranked severity predictions for every location at the given
    target timestamp.

    The severity score is a Tweedie-distributed continuous float representing
    the expected sum of (vehicle_weight × road_weight × violation_type_weight)
    across all violations at this location-hour.  A heavy-vehicle violation
    on a narrow 1-lane road ranks ABOVE many two-wheeler violations on a wide
    road — this is the key differentiator from the count-based heatmap.

    Algorithm:
      1. Parse and floor timestamp to the nearest hour.
      2. Build the 11-feature lookback vector for every location at once
         (vectorised numpy — same pattern as Part 1).
      3. naive_prediction    = same_hour_d1 (severity at same hour yesterday).
      4. baseline_prediction = recency-weighted dot product / weight_sum.
      5. lightgbm_prediction = LightGBM Tweedie model on 14 features.
      6. Merge in explainability fields (lane_count, dominant_vehicle_cat,
         dominant_violation) from the severity location metadata.
      7. Sort by lightgbm_prediction descending; assign integer rank (1 = riskiest).
    """
    # ── 1. Parse timestamp ────────────────────────────────────────
    try:
        target_ts = pd.Timestamp(timestamp).floor("h")
    except Exception:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot parse timestamp: '{timestamp}'. Use ISO-8601 format.",
        )

    state           = request.app.state
    pivot_data      = getattr(state, "severity_pivot_data", None)
    sev_loc_meta: pd.DataFrame = getattr(state, "severity_location_meta", pd.DataFrame())
    lgbm_severity   = getattr(state, "lgbm_severity", None)

    if pivot_data is None:
        raise HTTPException(
            status_code=503,
            detail="Severity panel not loaded. Run build_canonical_timeseries.py --target severity first.",
        )
    if lgbm_severity is None or not lgbm_severity.is_loaded:
        raise HTTPException(
            status_code=503,
            detail="Severity LightGBM model not loaded. Run train_models.py --target severity first.",
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

    # ── Filter: keep only locations with actual historical data ───
    # Same logic as the count-based endpoint: only locations where at
    # least one of the 11 lookback features is non-zero have real data
    # backing the severity prediction. All-zero rows are cold-start and
    # produce meaningless Tweedie prior scores.
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
        "SeverityPredict TS=%s  total_locs=%d  active_locs=%d (active_only=%s)",
        target_ts, n, n_active, active_only,
    )

    if n_active == 0:
        return []

    # ── 3–4. Naive + Baseline ─────────────────────────────────────
    naive_preds    = naive_predict(feat_mat_active)
    baseline_preds = baseline_predict(feat_mat_active)

    # ── 5. LightGBM (15 features) ────────────────────────────────
    wd  = target_ts.weekday()
    iwe = int(wd >= 5)
    ctx_cols = np.array([[target_ts.hour, wd, iwe, horizon_h]] * n_active, dtype=np.float32)
    X_lgbm = np.hstack([feat_mat_active, ctx_cols])

    lgbm_raw  = lgbm_severity.predict(X_lgbm)

    # Normalize Tweedie output to a 0–100 severity risk index.
    # The Tweedie model predicts values in the SAME range as training labels
    # (severity_score: min≈0.08, max≈160, mean≈1.57, p99≈11.6).
    # Unlike the count Poisson model (which outputs tiny 0.001–0.02 values),
    # NO ×1000 scaling is needed — applying it would give nonsense like 3951.
    # Instead we normalize by the dataset max (160) → score stays in 0–100.
    SEV_MAX = 160.0   # 99th-pct ≈ 11.6; absolute max ≈ 160 in training data
    lgbm_preds = np.clip(lgbm_raw / SEV_MAX * 100.0, 0, 100)

    # ── 6. Assemble + merge explainability fields ─────────────────
    result_df = pd.DataFrame({
        "location_key":        all_locs_active,
        "naive_prediction":    naive_preds.astype(float),
        "baseline_prediction": baseline_preds.astype(float),
        "lightgbm_prediction": lgbm_preds.astype(float),
    })

    merged = result_df.merge(sev_loc_meta, on="location_key", how="left")
    merged = merged.dropna(subset=["latitude", "longitude"])

    # ── 7. Sort + rank ────────────────────────────────────────────
    merged = merged.sort_values("lightgbm_prediction", ascending=False).reset_index(drop=True)
    merged["rank_lightgbm"] = range(1, len(merged) + 1)

    if top_n is not None:
        merged = merged.head(top_n)

    log.info(
        "SeverityPredict TS=%s  active_locs=%d  returned=%d  max_lgbm=%.4f",
        target_ts, n_active, len(merged),
        merged["lightgbm_prediction"].iloc[0] if len(merged) else 0,
    )

    # ── 8. Serialise ─────────────────────────────────────────────
    merged = merged.replace({np.nan: None})
    records = []
    for r in merged.to_dict("records"):
        lane = r.get("lane_count")
        records.append(SeverityPredictionRecord(
            location_key         = r["location_key"],
            latitude             = float(r["latitude"]),
            longitude            = float(r["longitude"]),
            area                 = r.get("area"),
            police_station       = r.get("police_station"),
            naive_prediction     = float(r["naive_prediction"]),
            baseline_prediction  = float(r["baseline_prediction"]),
            lightgbm_prediction  = float(r["lightgbm_prediction"]),
            rank_lightgbm        = int(r["rank_lightgbm"]),
            lane_count           = float(lane) if lane is not None and pd.notna(lane) else None,
            dominant_vehicle_cat = r.get("dominant_vehicle_cat"),
            dominant_violation   = r.get("dominant_violation"),
        ))
    return records
