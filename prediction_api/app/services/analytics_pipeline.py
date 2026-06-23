"""
analytics_pipeline.py — Build PIS scores, dark fleet, station stats,
hourly profiles, and persistence scores from raw data.

Called once at startup; results stored in app.state for all analytics endpoints.
"""
from __future__ import annotations

import csv as csv_mod
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _peek_header(csv_path: Path) -> List[str]:
    try:
        with open(csv_path, newline='', encoding='utf-8', errors='replace') as f:
            reader = csv_mod.reader(f)
            return next(reader, [])
    except Exception:
        return []


def _safe_float(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if np.isfinite(f) else default
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────
# PIS scores + hourly profiles  (from feature_engineered.csv)
# ─────────────────────────────────────────────────────────────────

def build_pis_and_profiles(
    raw_csv: Path,
    centrality_path: Path,
) -> Tuple[List[Dict], Dict[str, List[float]]]:
    """
    Returns (pis_records, hourly_profiles).

    pis_records: list of dicts, sorted by pis_score desc, with 'rank' added.
    hourly_profiles: {location_key: [mean_viol_h0, ..., mean_viol_h23]}
    """
    log.info("[Analytics] Loading %s for PIS / hourly profiles ...", raw_csv)

    # ── Load centrality cache ────────────────────────────────────────
    betweenness: Dict[str, float] = {}
    if centrality_path.exists():
        try:
            with open(centrality_path, encoding='utf-8') as f:
                cache = json.load(f)
            # Accept {loc_key: float} or {loc_key: {"betweenness": float, ...}}
            for k, v in cache.items():
                if isinstance(v, dict):
                    b = v.get('betweenness', v.get('betweenness_centrality', 0.0))
                else:
                    b = v
                betweenness[k] = _safe_float(b)
            log.info("[Analytics] Loaded betweenness for %d locations", len(betweenness))
        except Exception as exc:
            log.warning("[Analytics] centrality_cache load failed: %s", exc)

    # ── Load raw CSV (all columns — we need pcu_weight, lane_count etc.) ──
    raw = pd.read_csv(raw_csv, low_memory=False)
    bad = (
        raw["location_key"].isna()
        | (raw["location_key"].astype(str).str.strip() == "")
        | (raw["location_key"].astype(str).str.strip() == "No Junction")
    )
    raw = raw[~bad].copy()

    # Step 1 — drop unnamed grid cells (grid_X.XXX_Y.YYY) — not actionable by police
    grid_mask = raw["location_key"].astype(str).str.startswith("grid_")
    raw = raw[~grid_mask].copy()
    log.info("[Analytics] Raw CSV: %d rows, %d cols after grid filter (%d unique locations)",
             len(raw), raw.shape[1], raw["location_key"].nunique())

    # Parse hour_slot for time-range calculation
    if "hour_slot" in raw.columns:
        raw["hour_slot"] = pd.to_datetime(raw["hour_slot"], errors="coerce")

    # ── Hourly profiles ──────────────────────────────────────────────
    hourly_profiles: Dict[str, List[float]] = {}
    if "hour" in raw.columns and "violation_count" in raw.columns:
        hp = (
            raw.groupby(["location_key", "hour"])["violation_count"]
            .mean()
        )
        for loc in raw["location_key"].unique():
            profile = []
            for h in range(24):
                try:
                    val = hp.loc[(loc, h)] if (loc, h) in hp.index else 0.0
                except KeyError:
                    val = 0.0
                profile.append(_safe_float(val))
            hourly_profiles[loc] = profile
        log.info("[Analytics] Hourly profiles computed for %d locations", len(hourly_profiles))

    # ── Step 3: Enforcement failure rate from dataset.csv ────────────
    # feature_engineered.csv has no validation_status; load from dataset.csv
    enf_fail_map: Dict[str, float] = {}
    dataset_csv = raw_csv.parent / "dataset.csv"
    if dataset_csv.exists():
        try:
            header_ds = _peek_header(dataset_csv)
            ds_cols = [c for c in ["location_key", "validation_status"] if c in header_ds]
            if len(ds_cols) == 2:
                ds = pd.read_csv(dataset_csv, usecols=ds_cols, low_memory=False)
                ds = ds[ds["location_key"].notna()].copy()
                ds["rejected"] = ds["validation_status"].astype(str).str.upper() == "REJECTED"
                ds["has_status"] = ds["validation_status"].notna()
                agg = ds.groupby("location_key").agg(
                    rejected=("rejected", "sum"),
                    total=("has_status", "sum"),
                )
                agg = agg[agg["total"] > 0]
                enf_fail_map = (agg["rejected"] / agg["total"]).to_dict()
                log.info("[Analytics] Enforcement failure rates from dataset.csv: %d junctions", len(enf_fail_map))
            else:
                log.info("[Analytics] dataset.csv missing location_key/validation_status columns")
        except Exception as exc:
            log.warning("[Analytics] Enforcement map from dataset.csv failed: %s", exc)

    # ── PIS scores ───────────────────────────────────────────────────
    total_days = 1
    if "hour_slot" in raw.columns:
        ts_range = raw["hour_slot"].dropna()
        if len(ts_range):
            total_days = max(1, (ts_range.max() - ts_range.min()).days)

    has_violation_count = "violation_count" in raw.columns
    has_severity        = "severity_score" in raw.columns
    has_pcu             = "pcu_weight" in raw.columns
    has_lane            = "lane_count" in raw.columns
    has_val_status      = "validation_status" in raw.columns
    has_area            = "area" in raw.columns
    has_station         = "police_station" in raw.columns
    has_lat             = "latitude" in raw.columns
    has_lon             = "longitude" in raw.columns

    rows: List[Dict] = []
    for loc_key, grp in raw.groupby("location_key", sort=False):
        total_v = grp["violation_count"].sum() if has_violation_count else len(grp)
        violations_per_day = total_v / total_days

        mean_sev = _safe_float(grp["severity_score"].mean(), 0.0) if has_severity else 0.0
        mean_pcu = _safe_float(grp["pcu_weight"].mean(), 1.0) if has_pcu else 1.0
        mean_lane = _safe_float(grp["lane_count"].mean(), 2.0) if has_lane else 2.0
        if mean_lane < 0.1:
            mean_lane = 2.0

        # mean_blockage_severity: use severity_score if available, else derive from PCU / lane
        if mean_sev > 0:
            mean_blockage_sev = min(mean_sev, 7.0)
        else:
            mean_blockage_sev = min((mean_pcu / mean_lane) * 2.5, 7.0)

        b = betweenness.get(loc_key, 0.0)

        veh_hours_lost = violations_per_day * mean_pcu * 0.25  # 15-min avg delay
        loss_inr = veh_hours_lost * 500.0  # ₹500/PCU-hour

        # Step 3: use dataset.csv enforcement map (feature_engineered has no validation_status)
        enf_fail = enf_fail_map.get(str(loc_key), 0.0)
        if enf_fail == 0.0 and has_val_status:
            # fallback: read from raw if the column exists
            vs = grp["validation_status"].dropna()
            if len(vs):
                enf_fail = (vs.astype(str).str.upper() == "REJECTED").sum() / len(vs)

        area = grp["area"].dropna().iloc[0] if has_area and len(grp["area"].dropna()) else None
        station = (
            grp["police_station"].dropna().mode().iloc[0]
            if has_station and len(grp["police_station"].dropna())
            else None
        )

        # Step 2: extract lat/lon for the junction drawer
        try:
            lat_val = float(grp["latitude"].dropna().iloc[0]) if has_lat and len(grp["latitude"].dropna()) else None
        except (IndexError, ValueError, TypeError):
            lat_val = None
        try:
            lon_val = float(grp["longitude"].dropna().iloc[0]) if has_lon and len(grp["longitude"].dropna()) else None
        except (IndexError, ValueError, TypeError):
            lon_val = None

        pis = violations_per_day * (mean_blockage_sev + 0.1) * (b + 0.5)

        rows.append({
            "location_key":               str(loc_key),
            "area":                       str(area) if area is not None else None,
            "police_station":             str(station) if station is not None else None,
            "latitude":                   lat_val,
            "longitude":                  lon_val,
            "pis_score":                  pis,
            "vehicle_hours_lost_per_day": veh_hours_lost,
            "loss_inr_per_day":           loss_inr,
            "enforcement_failure_rate":   enf_fail,
            "mean_blockage_severity":     mean_blockage_sev,
            "betweenness":                b,
        })

    pis_records: List[Dict] = []
    if rows:
        df = pd.DataFrame(rows).sort_values("pis_score", ascending=False).reset_index(drop=True)
        # Use rank-based split so Monitor junctions remain visible even when
        # only the top-N by PIS score are returned to the frontend.
        n = len(df)
        cutoff = max(1, int(n * 0.7))
        df["action_type"] = ["Intervene"] * cutoff + ["Monitor"] * (n - cutoff)
        df["rank"] = range(1, n + 1)
        # pandas converts None→NaN in object columns; replace back to None so
        # Pydantic's Optional[str] validation passes (it rejects float NaN).
        for col in ("area", "police_station"):
            df[col] = df[col].where(df[col].notna(), other=None)
        pis_records = df.to_dict(orient="records")
        # Second pass: catch any remaining float NaN in string and numeric fields
        for rec in pis_records:
            for k in ("area", "police_station"):
                v = rec.get(k)
                if isinstance(v, float) and (v != v):  # NaN check
                    rec[k] = None
            for k in ("latitude", "longitude"):
                v = rec.get(k)
                if v is not None and isinstance(v, float) and (v != v):
                    rec[k] = None
        log.info("[Analytics] PIS scores computed for %d junctions", len(pis_records))

    return pis_records, hourly_profiles


# ─────────────────────────────────────────────────────────────────
# Dark fleet + station stats  (from dataset.csv — vehicle-level)
# ─────────────────────────────────────────────────────────────────

def build_dark_fleet_and_station_stats(
    dataset_csv: Path,
) -> Tuple[List[Dict], Dict[str, Set[str]], List[Dict]]:
    """
    Returns (dark_fleet, fleet_station_map, station_stats).

    dark_fleet: list of vehicle dicts sorted by total_hits desc
    fleet_station_map: {police_station: set_of_vehicle_numbers}
    station_stats: list of per-station dicts sorted by total_violations desc
    """
    dark_fleet: List[Dict] = []
    fleet_station_map: Dict[str, Set[str]] = {}
    station_stats: List[Dict] = []

    if not dataset_csv.exists():
        log.warning("[Analytics] dataset.csv not found at %s — dark fleet / station stats unavailable", dataset_csv)
        return dark_fleet, fleet_station_map, station_stats

    log.info("[Analytics] Loading %s (vehicle-level data)...", dataset_csv)
    header = _peek_header(dataset_csv)
    if not header:
        return dark_fleet, fleet_station_map, station_stats

    # ── Dark fleet columns ───────────────────────────────────────────
    df_cols = [c for c in ["vehicle_number", "location_key", "police_station"] if c in header]
    stat_cols = [c for c in ["police_station", "validation_status", "device_id", "created_datetime", "validation_timestamp"] if c in header]
    all_cols = list(dict.fromkeys(df_cols + stat_cols))  # deduplicated

    if not all_cols:
        log.warning("[Analytics] No usable columns found in dataset.csv header: %s", header[:20])
        return dark_fleet, fleet_station_map, station_stats

    try:
        df = pd.read_csv(dataset_csv, usecols=all_cols, low_memory=False)
        log.info("[Analytics] dataset.csv loaded: %d rows, %d cols", len(df), len(df.columns))
    except Exception as exc:
        log.warning("[Analytics] dataset.csv load failed: %s", exc)
        return dark_fleet, fleet_station_map, station_stats

    # ── Dark fleet ───────────────────────────────────────────────────
    if "vehicle_number" in df.columns:
        df["vehicle_number"] = df["vehicle_number"].astype(str).str.strip()
        fleet_df = df.dropna(subset=["vehicle_number"])
        fleet_df = fleet_df[fleet_df["vehicle_number"] != "nan"]

        agg: Dict[str, Any] = {"total_hits": ("vehicle_number", "count")}
        if "location_key" in fleet_df.columns:
            agg["distinct_junctions"] = ("location_key", "nunique")
        else:
            agg["distinct_junctions"] = ("vehicle_number", "nunique")

        hits = fleet_df.groupby("vehicle_number").agg(**agg).reset_index()
        hits["fleet_cluster_id"] = hits["vehicle_number"].str[:4]
        cluster_max = hits.groupby("fleet_cluster_id")["total_hits"].transform("max")
        hits["is_fleet_leader"] = hits["total_hits"] == cluster_max

        repeat = hits[hits["total_hits"] >= 5].sort_values("total_hits", ascending=False)
        dark_fleet = [
            {
                "vehicle_number":    str(r["vehicle_number"]),
                "total_hits":        int(r["total_hits"]),
                "distinct_junctions": int(r.get("distinct_junctions", 0)),
                "fleet_cluster_id":  str(r["fleet_cluster_id"]),
                "is_fleet_leader":   bool(r["is_fleet_leader"]),
            }
            for _, r in repeat.head(200).iterrows()
        ]
        log.info(
            "[Analytics] Dark fleet: %d repeat offenders (5+ hits) of %d total vehicles",
            len(dark_fleet),
            len(hits),
        )

        # Build station → vehicles mapping
        if "police_station" in fleet_df.columns:
            for _, row in fleet_df[["vehicle_number", "police_station"]].dropna().iterrows():
                s = str(row["police_station"])
                v = str(row["vehicle_number"])
                fleet_station_map.setdefault(s, set()).add(v)

    # ── Station stats ────────────────────────────────────────────────
    if "police_station" in df.columns:
        df = df.dropna(subset=["police_station"])

        for station, sgrp in df.groupby("police_station"):
            total_v = len(sgrp)

            rej_rate = 0.0
            if "validation_status" in sgrp.columns:
                vs = sgrp["validation_status"].dropna()
                if len(vs):
                    rej_rate = (vs.astype(str).str.upper() == "REJECTED").sum() / len(vs)

            vio_per_device = 0.0
            if "device_id" in sgrp.columns:
                n_dev = sgrp["device_id"].nunique()
                vio_per_device = total_v / max(n_dev, 1)

            lag_hours: Optional[float] = None
            if "created_datetime" in sgrp.columns and "validation_timestamp" in sgrp.columns:
                try:
                    cd = pd.to_datetime(sgrp["created_datetime"], errors="coerce")
                    vt = pd.to_datetime(sgrp["validation_timestamp"], errors="coerce")
                    lag = (vt - cd).dt.total_seconds() / 3600.0
                    lag = lag.dropna()
                    lag = lag[lag >= 0]
                    if len(lag):
                        lag_hours = float(lag.median())
                except Exception:
                    pass

            station_stats.append({
                "police_station":             str(station),
                "total_violations":           int(total_v),
                "rejection_rate":             float(rej_rate),
                "violations_per_device":      float(vio_per_device),
                "median_validation_lag_hours": lag_hours,
                "flag_high_rejection":        bool(rej_rate > 0.35),
            })

        station_stats.sort(key=lambda x: x["total_violations"], reverse=True)
        log.info("[Analytics] Station stats: %d stations", len(station_stats))

    return dark_fleet, fleet_station_map, station_stats


# ─────────────────────────────────────────────────────────────────
# Persistence scores  (from count pivot matrix)
# ─────────────────────────────────────────────────────────────────

def build_persistence_scores(pivot_data) -> Dict[str, float]:
    """
    For each location, compute: weeks_with_any_violation / total_weeks.
    Uses the pre-built pivot matrix (n_hours × n_locs).
    """
    log.info("[Analytics] Computing persistence scores from pivot matrix...")
    try:
        timestamps = pivot_data.timestamps
        matrix = pivot_data.matrix  # (n_hours, n_locs)

        # Week key per timestamp row
        week_keys = np.array(
            [ts.year * 100 + ts.isocalendar()[1] for ts in timestamps],
            dtype=np.int32,
        )
        unique_weeks = np.unique(week_keys)
        n_weeks = len(unique_weeks)
        if n_weeks == 0:
            return {}

        n_locs = matrix.shape[1]
        weeks_active = np.zeros(n_locs, dtype=np.int32)
        for w in unique_weeks:
            mask = week_keys == w
            weeks_active += (matrix[mask].sum(axis=0) > 0).astype(np.int32)

        persistence = weeks_active / n_weeks
        scores = {
            loc: float(persistence[pos])
            for loc, pos in pivot_data.loc_to_pos.items()
        }
        log.info("[Analytics] Persistence scores: %d locations over %d weeks", len(scores), n_weeks)
        return scores
    except Exception as exc:
        log.warning("[Analytics] Persistence score computation failed: %s", exc)
        return {}
