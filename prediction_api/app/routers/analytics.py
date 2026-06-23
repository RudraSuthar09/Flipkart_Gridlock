"""
analytics.py — Analytics endpoints: PIS Dashboard, Dark Fleet,
Station Stats, Hourly Profiles, Persistence Scores.

All data is precomputed at startup and served from app.state.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Query, Request
from app.schemas import (
    BatchHourlyRequest,
    DarkFleetRecord,
    HourlyProfileRecord,
    PISRecord,
    StationStatsRecord,
)

router = APIRouter()


@router.get("/pis-scores", response_model=List[PISRecord])
async def get_pis_scores(
    request: Request,
    top_n: int = Query(default=337, ge=1, le=1000),
    action_type: Optional[str] = None,
):
    """
    Ranked PIS (Priority Impact Score) table — one row per junction.
    Sort: highest PIS first. Pass action_type=Intervene to filter.
    """
    records: List[dict] = getattr(request.app.state, "pis_scores", [])
    if action_type:
        records = [r for r in records if r.get("action_type") == action_type]
    return records[:top_n]


@router.get("/dark-fleet", response_model=List[DarkFleetRecord])
async def get_dark_fleet(
    request: Request,
    police_station: Optional[str] = None,
    min_hits: int = Query(default=5, ge=1),
    top_n: int = Query(default=50, ge=1, le=200),
):
    """
    Repeat-offender vehicle list. Filter by police_station jurisdiction.
    Only vehicles with >= min_hits violations are returned.
    """
    records: List[dict] = getattr(request.app.state, "dark_fleet", [])
    if min_hits > 5:
        records = [r for r in records if r["total_hits"] >= min_hits]

    if police_station:
        station_map: Dict[str, set] = getattr(request.app.state, "fleet_station_map", {})
        vehicle_set = station_map.get(police_station, set())
        records = [r for r in records if r["vehicle_number"] in vehicle_set]

    return records[:top_n]


@router.get("/station-stats", response_model=List[StationStatsRecord])
async def get_station_stats(request: Request):
    """Per-station validation KPIs: rejection rate, throughput, lag."""
    return getattr(request.app.state, "station_stats", [])


@router.get("/hourly-profile", response_model=List[HourlyProfileRecord])
async def get_hourly_profile(
    request: Request,
    location_key: str,
):
    """
    24-hour violation distribution for a given location_key.
    Returns mean violation count for hours 0–23 across historical data.
    """
    profiles: Dict[str, List[float]] = getattr(request.app.state, "hourly_profiles", {})
    profile = profiles.get(location_key)
    if profile is None:
        return [{"hour": h, "mean_violations": 0.0} for h in range(24)]
    return [{"hour": h, "mean_violations": float(v)} for h, v in enumerate(profile)]


@router.post("/hourly-profiles/batch")
async def get_hourly_profiles_batch(
    request: Request,
    body: BatchHourlyRequest,
) -> Dict[str, List[float]]:
    """
    Return 24-hour violation profiles for a list of location_keys in one round-trip.
    Missing keys get a flat [0.0]*24 profile rather than a 404.
    """
    profiles: Dict[str, List[float]] = getattr(request.app.state, "hourly_profiles", {})
    return {k: profiles.get(k, [0.0] * 24) for k in body.location_keys}


@router.get("/persistence")
async def get_persistence_scores(
    request: Request,
    location_key: Optional[str] = None,
) -> Dict[str, float]:
    """
    Persistence scores: fraction of weeks with any violation per location.
    Pass location_key for a single lookup; omit for the full dict.
    """
    scores: Dict[str, float] = getattr(request.app.state, "persistence_scores", {})
    if location_key:
        return {location_key: scores.get(location_key, 0.0)}
    return scores
