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
    location_key:    str
    latitude:        float
    longitude:       float
    area:            Optional[str]   = None
    police_station:  Optional[str]   = None
    # OSM road class fields (present when road_class_lookup.json is loaded)
    highway:         Optional[str]   = Field(None, description="OSM highway tag (primary, secondary, etc.)")
    road_tier:       Optional[int]   = Field(None, description="Road capacity tier 0-5 (0=motorway, 5=service lane)")
    road_weight_osm: Optional[float] = Field(None, description="OSM-derived road impact weight (lower=wider road)")
    road_label:      Optional[str]   = Field(None, description="Human-readable road type label")
    is_oneway:       Optional[bool]  = Field(None, description="True if road is one-way")
    osm_road_name:   Optional[str]   = Field(None, description="OSM road name")

    model_config = {"from_attributes": True}


# ── Prediction row (for /predict endpoint) ────────────────────────────────
class PredictionRecord(BaseModel):
    location_key:           str
    latitude:               float
    longitude:              float
    area:                   Optional[str]   = None
    police_station:         Optional[str]   = None
    # OSM road class fields
    highway:                Optional[str]   = None
    road_tier:              Optional[int]   = None
    road_weight_osm:        Optional[float] = None
    road_label:             Optional[str]   = None
    is_oneway:              Optional[bool]  = None
    osm_road_name:          Optional[str]   = None
    # Three prediction scores
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
    lane data and OSM road class data.
    """
    location_key:         str
    latitude:             float
    longitude:            float
    area:                 Optional[str]   = None
    police_station:       Optional[str]   = None
    # Lane / road data (from feature_engineered.csv)
    lane_count:           Optional[float] = Field(None, description="Avg lane count for this location")
    dominant_vehicle_cat: Optional[str]   = Field(None, description="Most common vehicle category at this location")
    dominant_violation:   Optional[str]   = Field(None, description="Most common violation type at this location")
    # OSM road class fields
    highway:              Optional[str]   = Field(None, description="OSM highway tag")
    road_tier:            Optional[int]   = Field(None, description="Road capacity tier 0-5")
    road_weight_osm:      Optional[float] = Field(None, description="OSM-derived road impact weight")
    road_label:           Optional[str]   = Field(None, description="Human-readable road type")
    is_oneway:            Optional[bool]  = Field(None, description="One-way road flag")
    osm_road_name:        Optional[str]   = Field(None, description="OSM road name")

    model_config = {"from_attributes": True}


class SeverityPredictionRecord(BaseModel):
    """
    /api/v1/traffic-severity/predict — severity-weighted prediction row.
    Severity scores are continuous floats (Tweedie-distributed), not
    integer counts — do NOT compare magnitudes directly with Part 1.
    """
    location_key:         str
    latitude:             float
    longitude:            float
    area:                 Optional[str]   = None
    police_station:       Optional[str]   = None
    # Three severity prediction scores
    naive_prediction:     float = Field(description="Same hour yesterday severity (naive baseline)")
    baseline_prediction:  float = Field(description="Recency-weighted severity baseline")
    lightgbm_prediction:  float = Field(description="LightGBM Tweedie severity prediction")
    # Rank by LightGBM severity; 1 = highest severity risk
    rank_lightgbm:        int   = Field(description="Severity rank (1 = highest predicted severity)")
    # Explainability context — violation dataset fields
    lane_count:           Optional[float] = Field(None, description="Road lane count")
    dominant_vehicle_cat: Optional[str]   = Field(None, description="Most common vehicle category")
    dominant_violation:   Optional[str]   = Field(None, description="Most common violation type")
    # OSM road class fields
    highway:              Optional[str]   = Field(None, description="OSM highway tag")
    road_tier:            Optional[int]   = Field(None, description="Road capacity tier 0-5")
    road_weight_osm:      Optional[float] = Field(None, description="OSM-derived road impact weight")
    road_label:           Optional[str]   = Field(None, description="Human-readable road type")
    is_oneway:            Optional[bool]  = Field(None, description="One-way road flag")
    osm_road_name:        Optional[str]   = Field(None, description="OSM road name")

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════
# Analytics schemas (PIS Dashboard, Dark Fleet, Station Stats)
# ══════════════════════════════════════════════════════════════════════════

class PISRecord(BaseModel):
    rank: int
    location_key: str
    area: Optional[str] = None
    police_station: Optional[str] = None
    latitude:  Optional[float] = None
    longitude: Optional[float] = None
    pis_score: float
    vehicle_hours_lost_per_day: float
    loss_inr_per_day: float
    enforcement_failure_rate: float
    mean_blockage_severity: float
    betweenness: float
    action_type: str  # 'Intervene' | 'Monitor'

    model_config = {"from_attributes": True}


class DarkFleetRecord(BaseModel):
    vehicle_number: str
    total_hits: int
    distinct_junctions: int
    fleet_cluster_id: str
    is_fleet_leader: bool

    model_config = {"from_attributes": True}


class StationStatsRecord(BaseModel):
    police_station: str
    total_violations: int
    rejection_rate: float
    violations_per_device: float
    median_validation_lag_hours: Optional[float] = None
    flag_high_rejection: bool

    model_config = {"from_attributes": True}


class HourlyProfileRecord(BaseModel):
    hour: int
    mean_violations: float


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
