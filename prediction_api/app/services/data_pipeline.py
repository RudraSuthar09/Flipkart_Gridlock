"""
data_pipeline.py — Load the raw feature-engineering CSV and produce the
canonical dense per-location hourly panel used by all models.

Pipeline (§4 of the spec):
  4.1  load_and_validate()     → raw DataFrame with sanity checks
  4.2  build_location_master() → one row per location_key
  4.3  aggregate_to_grain()    → one row per (location_key, hour_slot)
  4.4  get_date_range()        → (min_ts, max_ts)
  4.5  densify()               → complete hourly grid, zeros filled in
       save_panel()            → write parquet

All functions are pure (no global state) for easy unit testing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from app.config import (
    RAW_CSV,
    PARQUET_PATH,
    PARQUET_SEVERITY_PATH,
    PART1_COLS,
    SEVERITY_PART1_COLS,
    VIOLATION_ONEHOT_PREFIX,
    PROCESSED_DIR,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# 4.1  Load & validate
# ─────────────────────────────────────────────────────────────────

def load_and_validate(csv_path: Path = RAW_CSV) -> pd.DataFrame:
    """
    Read the feature_engineered CSV, run sanity checks (§4.1), and
    return a clean DataFrame with only the Part-1 columns we need.

    Sanity checks:
    - Logs a warning (does NOT crash) for rows where sum(one-hot cols)
      != violation_count — these indicate upstream data bugs.
    - Drops rows where location_key is null/empty/"No Junction".
    - Parses hour_slot to datetime.
    """
    log.info("Loading CSV from %s", csv_path)
    raw = pd.read_csv(csv_path, low_memory=False)
    log.info("Loaded %d rows, %d columns", len(raw), len(raw.columns))

    # ── Parse hour_slot ───────────────────────────────────────────
    raw["hour_slot"] = pd.to_datetime(raw["hour_slot"], errors="coerce")
    n_bad_ts = raw["hour_slot"].isna().sum()
    if n_bad_ts:
        log.warning("%d rows have unparseable hour_slot — dropping", n_bad_ts)
        raw = raw.dropna(subset=["hour_slot"])

    # ── One-hot sum sanity check (§4.1) ───────────────────────────
    # Identify one-hot columns by the "--" separator in column name
    onehot_cols = [c for c in raw.columns if VIOLATION_ONEHOT_PREFIX in c]
    log.info("Found %d one-hot violation columns", len(onehot_cols))

    if onehot_cols:
        onehot_sum = raw[onehot_cols].sum(axis=1)
        mismatch_mask = onehot_sum != raw["violation_count"]
        n_mismatch = mismatch_mask.sum()
        if n_mismatch:
            log.warning(
                "One-hot sum != violation_count for %d rows (%.1f%%). "
                "Upstream data bug suspected. Rows retained but flagged.",
                n_mismatch,
                100.0 * n_mismatch / len(raw),
            )

    # ── Drop bad location_key rows (§4.1) ─────────────────────────
    bad_keys = (
        raw["location_key"].isna()
        | (raw["location_key"].astype(str).str.strip() == "")
        | (raw["location_key"].astype(str).str.strip() == "No Junction")
    )
    n_bad = bad_keys.sum()
    if n_bad:
        log.warning(
            "Dropping %d rows with null/empty/'No Junction' location_key", n_bad
        )
        raw = raw[~bad_keys].copy()

    # ── Keep only Part-1 columns (§2) ─────────────────────────────
    # Add weekday/is_weekend which come from the CSV already
    keep = PART1_COLS + ["weekday", "is_weekend"]
    keep = [c for c in keep if c in raw.columns]   # defensive: only keep what exists
    df = raw[keep].copy()

    log.info("After cleaning: %d rows, %d columns", len(df), len(df.columns))
    return df


def load_severity_and_validate(csv_path: Path = RAW_CSV) -> pd.DataFrame:
    """
    Load feature_engineered CSV for Part 2 (severity_score target).
    Keeps severity_score and lane_count alongside the standard columns.

    severity_score is confirmed as SUM(pcu_i × road_weight × vt_weight_i)
    per bucket — correctly aggregated at source (verified: row with
    violation_count=5 has severity_score=1.75, not 0.35 average).
    No recomputation from raw violation rows is needed.
    """
    log.info("Loading CSV (severity target) from %s", csv_path)
    raw = pd.read_csv(csv_path, low_memory=False)
    log.info("Loaded %d rows, %d columns", len(raw), len(raw.columns))

    raw["hour_slot"] = pd.to_datetime(raw["hour_slot"], errors="coerce")
    raw = raw.dropna(subset=["hour_slot"])

    bad_keys = (
        raw["location_key"].isna()
        | (raw["location_key"].astype(str).str.strip() == "")
        | (raw["location_key"].astype(str).str.strip() == "No Junction")
    )
    raw = raw[~bad_keys].copy()

    keep = SEVERITY_PART1_COLS + ["weekday", "is_weekend"]
    keep = [c for c in keep if c in raw.columns]
    df = raw[keep].copy()

    # Ensure severity_score is non-negative float
    df["severity_score"] = df["severity_score"].clip(lower=0).fillna(0).astype(np.float32)

    log.info("Severity data: %d rows, %d columns", len(df), len(df.columns))
    return df




# ─────────────────────────────────────────────────────────────────
# 4.2  Location master table
# ─────────────────────────────────────────────────────────────────

def build_location_master(df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per unique location_key.

    Latitude/longitude choice: FIRST non-null value per location_key.
    Rationale: lat/lon can vary slightly across rows for the same junction
    (GPS noise / different incident positions). Taking the first observed
    value is stable and reproducible; the alternative (mean) would change
    every time a new row arrives. Documented here per §4.2.

    area: first non-null
    police_station: mode (most common value)
    """
    log.info("Building location master table")

    def first_non_null(series: pd.Series):
        valid = series.dropna()
        return valid.iloc[0] if len(valid) else None

    def mode_or_null(series: pd.Series):
        valid = series.dropna()
        if len(valid) == 0:
            return None
        return valid.mode().iloc[0]

    master = (
        df.groupby("location_key", sort=False)
        .agg(
            latitude       = ("latitude",       first_non_null),
            longitude      = ("longitude",       first_non_null),
            area           = ("area",            first_non_null),
            police_station = ("police_station",  mode_or_null),
        )
        .reset_index()
    )

    # Drop rows where we couldn't determine lat/lon (unmappable)
    before = len(master)
    master = master.dropna(subset=["latitude", "longitude"])
    dropped = before - len(master)
    if dropped:
        log.warning("Dropped %d locations with no valid lat/lon", dropped)

    log.info("Location master: %d locations", len(master))
    return master


# ─────────────────────────────────────────────────────────────────
# 4.3  Aggregate to canonical grain
# ─────────────────────────────────────────────────────────────────

def aggregate_to_grain(
    df: pd.DataFrame,
    value_column: str = "violation_count",
) -> pd.DataFrame:
    """
    Collapse any duplicate (location_key, hour_slot) rows by summing
    the target value_column. weekday/is_weekend are deterministic from
    the timestamp so we take max (equivalent to first here).

    value_column: 'violation_count' (Part 1) or 'severity_score' (Part 2)
    """
    log.info("Aggregating '%s' to (location_key, hour_slot) grain", value_column)
    grp = df.groupby(["location_key", "hour_slot"], sort=True)

    vc  = grp[value_column].sum().rename(value_column)
    wd  = grp["weekday"].max()
    iwe = grp["is_weekend"].max()

    agg = pd.concat([vc, wd, iwe], axis=1).reset_index()
    log.info("After aggregation: %d unique (location, hour) pairs", len(agg))
    return agg


# ─────────────────────────────────────────────────────────────────
# 4.4  Full date range
# ─────────────────────────────────────────────────────────────────

def get_date_range(agg: pd.DataFrame) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """Return (min_hour_slot, max_hour_slot) across the whole dataset."""
    min_ts = agg["hour_slot"].min()
    max_ts = agg["hour_slot"].max()
    log.info("Dataset date range: %s → %s", min_ts, max_ts)
    return min_ts, max_ts


# ─────────────────────────────────────────────────────────────────
# 4.5  Densify — THE CRITICAL STEP
# ─────────────────────────────────────────────────────────────────

def densify(
    agg: pd.DataFrame,
    min_ts: pd.Timestamp,
    max_ts: pd.Timestamp,
    value_column: str = "violation_count",
) -> pd.DataFrame:
    """
    For every location_key, reindex its sparse time series across EVERY
    hour in [min_ts, max_ts] and fill missing values with 0.

    value_column: 'violation_count' (int32, Part 1) or
                  'severity_score'  (float32, Part 2)

    WITHOUT this step: .shift() / timestamp-based lookups on the sparse
    frame would silently return the WRONG prior event instead of 0 for
    hours with no violations. This is the most common silent bug in
    event-rate modelling on sparse data.

    Result columns: location_key, timestamp, <value_column>
    """
    log.info("Densifying panel (value_column=%s): filling zero-value hours", value_column)
    full_index = pd.date_range(start=min_ts, end=max_ts, freq="h")
    total_hours = len(full_index)
    log.info(
        "Full hourly grid: %d hours × %d locations = ~%d rows",
        total_hours,
        agg["location_key"].nunique(),
        total_hours * agg["location_key"].nunique(),
    )

    agg_indexed = agg.set_index("hour_slot")
    is_float = value_column == "severity_score"

    chunks = []
    for loc_key, group in agg_indexed.groupby("location_key"):
        loc_series = group[value_column]
        dense_series = loc_series.reindex(full_index, fill_value=0)
        chunk = pd.DataFrame(
            {
                "location_key": loc_key,
                "timestamp":    full_index,
                value_column:   dense_series.values,
            }
        )
        chunks.append(chunk)

    panel = pd.concat(chunks, ignore_index=True)
    if is_float:
        panel[value_column] = panel[value_column].astype(np.float32)
    else:
        panel[value_column] = panel[value_column].astype(np.int32)
    panel["timestamp"] = pd.to_datetime(panel["timestamp"])

    # Rename to 'violation_count' so downstream feature_engineering is unchanged
    # for the count target; for severity we rename to allow feature_engineering
    # to treat the column generically.
    if value_column != "violation_count":
        panel = panel.rename(columns={value_column: "violation_count"})
        log.info(
            "Note: '%s' column renamed to 'violation_count' in panel for "
            "compatibility with feature_engineering.py.",
            value_column,
        )

    log.info(
        "Dense panel: %d rows, %d unique locations",
        len(panel),
        panel["location_key"].nunique(),
    )
    return panel


# ─────────────────────────────────────────────────────────────────
# Save / Load helpers
# ─────────────────────────────────────────────────────────────────

def save_panel(panel: pd.DataFrame, path: Path = PARQUET_PATH) -> None:
    """Write the dense panel as parquet (fast columnar I/O for large frames)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(path, index=False, compression="snappy")
    log.info("Panel saved → %s  (%d rows)", path, len(panel))


def load_panel(path: Path = PARQUET_PATH) -> pd.DataFrame:
    """Read the dense panel parquet back into memory."""
    if not path.exists():
        raise FileNotFoundError(
            f"Dense panel not found at {path}. "
            "Run scripts/build_canonical_timeseries.py first."
        )
    panel = pd.read_parquet(path)
    ts = pd.to_datetime(panel["timestamp"])
    # Strip timezone if present so lookups against naive target timestamps work
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    panel["timestamp"] = ts
    log.info("Panel loaded from %s  (%d rows)", path, len(panel))
    return panel


def build_pipeline(
    csv_path: Path = RAW_CSV,
    parquet_path: Path = PARQUET_PATH,
    target: str = "count",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run the full pipeline and return (panel_df, location_master_df).
    The panel is also saved to parquet_path.

    target: 'count'    → violation_count (Part 1)
            'severity' → severity_score  (Part 2)
    """
    if target == "severity":
        df = load_severity_and_validate(csv_path)
        value_column = "severity_score"
    else:
        df = load_and_validate(csv_path)
        value_column = "violation_count"

    location_master = build_location_master(df)
    agg             = aggregate_to_grain(df, value_column=value_column)
    min_ts, max_ts  = get_date_range(agg)
    panel           = densify(agg, min_ts, max_ts, value_column=value_column)
    save_panel(panel, parquet_path)
    return panel, location_master
