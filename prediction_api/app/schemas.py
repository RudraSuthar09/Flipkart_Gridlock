"""
schemas.py — Pydantic request/response models for the prediction API.
FastAPI validates all inputs/outputs against these; they also auto-generate
the OpenAPI docs at /docs.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


# ── Location (for /locations endpoint) ────────────────────────────────────
class LocationRecord(BaseModel):
    location_key:   str
    latitude:       float
    longitude:      float
    area:           Optional[str] = None
    police_station: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Prediction row (for /predict endpoint) ────────────────────────────────
class PredictionRecord(BaseModel):
    location_key:           str
    latitude:               float
    longitude:              float
    area:                   Optional[str] = None
    police_station:         Optional[str] = None

    # Three prediction scores — all on the same scale as violation_count
    naive_prediction:       float = Field(description="Same hour yesterday (simplest baseline)")
    baseline_prediction:    float = Field(description="Recency-weighted sum of 11 lookback features")
    lightgbm_prediction:    float = Field(description="LightGBM Poisson regression on same features")

    # Rank by LightGBM score; 1 = riskiest
    rank_lightgbm: int = Field(description="Rank by lightgbm_prediction descending (1=riskiest)")


# ── Health response ────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status:              str
    model_loaded:        bool
    panel_rows:          int
    panel_last_updated:  str   # ISO timestamp string
    location_count:      int


# ══════════════════════════════════════════════════════════════════════════
# Part 2 — Severity schemas
# ══════════════════════════════════════════════════════════════════════════

class SeverityLocationRecord(BaseModel):
    """
    /api/v1/traffic-severity/locations — extends LocationRecord with
    lane data for the data-confidence map layer.
    """
    location_key:         str
    latitude:             float
    longitude:            float
    area:                 Optional[str]   = None
    police_station:       Optional[str]   = None

    # Lane / road data (from feature_engineered.csv)
    lane_count:           Optional[float] = Field(None, description="OSM/avg lane count for this location")
    dominant_vehicle_cat: Optional[str]   = Field(None, description="Most common vehicle category at this location")
    dominant_violation:   Optional[str]   = Field(None, description="Most common violation type at this location")

    model_config = {"from_attributes": True}


class SeverityPredictionRecord(BaseModel):
    """
    /api/v1/traffic-severity/predict — severity-weighted prediction row.
    Severity scores are continuous floats (Tweedie-distributed), not
    integer counts — do NOT compare magnitudes directly with Part 1.
    """
    location_key:   str
    latitude:       float
    longitude:      float
    area:           Optional[str]   = None
    police_station: Optional[str]   = None

    # Three severity prediction scores
    naive_prediction:       float = Field(description="Same hour yesterday severity (naive baseline)")
    baseline_prediction:    float = Field(description="Recency-weighted severity baseline")
    lightgbm_prediction:    float = Field(description="LightGBM Tweedie severity prediction")

    # Rank by LightGBM severity; 1 = highest severity risk
    rank_lightgbm: int = Field(description="Severity rank (1 = highest predicted severity)")

    # Explainability context
    lane_count:           Optional[float] = Field(None, description="Road lane count (lower = higher congestion impact)")
    dominant_vehicle_cat: Optional[str]   = Field(None, description="Most common vehicle category recently at this location")
    dominant_violation:   Optional[str]   = Field(None, description="Most common violation type at this location")

    model_config = {"from_attributes": True}


class SeverityHealthResponse(BaseModel):
    """
    /api/v1/traffic-severity/health — includes data-quality coverage metrics
    so operators always know what fraction of severity scores are on verified data.
    """
    status:                   str
    model_loaded:             bool
    panel_rows:               int
    panel_last_updated:       str    # ISO timestamp string
    location_count:           int

    # Coverage metrics (§2.A.3 + §4.3 from spec)
    vehicle_mapping_coverage: float = Field(
        description="Fraction of vehicle type codes with a confirmed PCU mapping (1.0 = 100%)"
    )
    lane_match_coverage:      float = Field(
        description="Fraction of locations where lane_count is a real OSM/data value (not None/default)"
    )
