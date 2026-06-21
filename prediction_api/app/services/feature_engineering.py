"""
feature_engineering.py — Build the 11-feature lookback vector for any
(location_key, target_timestamp) pair, fully vectorized.

§5 feature spec (fixed order, must not change between train and inference):
  recent_h1, recent_h2, recent_h3, recent_h4
      = violation_count at t-1h, t-2h, t-3h, t-4h

  same_hour_d1, same_hour_d2, same_hour_d3, same_hour_d4
      = violation_count at t-24h, t-48h, t-72h, t-96h

  same_hour_wd_w1, same_hour_wd_w2, same_hour_wd_w3
      = violation_count at t-7d, t-14d, t-21d

Cold-start rule: if the lookup timestamp falls before the panel's start,
fill with 0.  Young locations naturally score low — do NOT drop them.

Vectorisation strategy:
  Pivot the dense panel once into a 2-D numpy matrix
  (rows = hours, cols = locations).  Then for every offset, convert the
  batch of (target_timestamp, location_key) pairs to (row_idx, col_idx)
  integer arrays and do a single numpy fancy-index read — O(batch) work
  per offset, NOT a Python loop over rows.
"""
from __future__ import annotations

import logging
from typing import Dict, List, NamedTuple, Tuple

import numpy as np
import pandas as pd

from app.config import (
    FEATURE_NAMES,
    CONTEXT_FEATURES,
    ALL_LGBM_FEATURES,
    MIN_HISTORY_DAYS,
)

log = logging.getLogger(__name__)

# Offsets in hours, matching FEATURE_NAMES order exactly
_OFFSETS_H: List[int] = [
    1, 2, 3, 4,          # recent_h1..h4
    24, 48, 72, 96,      # same_hour_d1..d4
    168, 336, 504,       # same_hour_wd_w1..w3  (7×24, 14×24, 21×24)
]
assert len(_OFFSETS_H) == len(FEATURE_NAMES), "Offset count must match feature names"


# ─────────────────────────────────────────────────────────────────
# Pivot data container — built once, reused for all predictions
# ─────────────────────────────────────────────────────────────────

class PivotData(NamedTuple):
    """
    Immutable container holding the pre-pivoted panel matrix and
    the two index maps needed for O(1) numpy lookups.
    """
    matrix:     np.ndarray              # shape (n_hours, n_locs), dtype int32
    ts_to_pos:  Dict[pd.Timestamp, int] # timestamp  → row index
    loc_to_pos: Dict[str, int]          # location_key → col index
    timestamps: pd.DatetimeIndex        # ordered timestamps (for date-range checks)
    panel_start: pd.Timestamp
    panel_end:   pd.Timestamp


def build_pivot_matrix(panel_df: pd.DataFrame) -> PivotData:
    """
    Pivot the dense panel (location_key, timestamp, violation_count) into
    a 2-D numpy matrix [timestamp × location_key].

    Called ONCE at model-load time; the returned PivotData is kept in
    memory and shared across all prediction requests.

    Memory footprint:
      ~6,333 locations × ~3,623 hours × 4 bytes (int32) ≈ 87 MB — acceptable.
    """
    log.info("Building pivot matrix from panel (%d rows)...", len(panel_df))
    # panel already has one row per (location_key, timestamp) with no dupes —
    # pivot() is faster than pivot_table() because it skips the aggregation step.
    pivot = (
        panel_df
        .pivot(index="timestamp", columns="location_key", values="violation_count")
        .fillna(0)
        .astype(np.int32)
    )
    matrix     = pivot.values                            # (n_hours, n_locs)
    timestamps = pd.DatetimeIndex(pivot.index)
    locs       = list(pivot.columns)

    ts_to_pos  = {ts: i for i, ts in enumerate(timestamps)}
    loc_to_pos = {loc: j for j, loc in enumerate(locs)}

    log.info(
        "Pivot matrix: %d hours × %d locations  (%.1f MB)",
        len(timestamps), len(locs),
        matrix.nbytes / 1e6,
    )
    return PivotData(
        matrix      = matrix,
        ts_to_pos   = ts_to_pos,
        loc_to_pos  = loc_to_pos,
        timestamps  = timestamps,
        panel_start = timestamps.min(),
        panel_end   = timestamps.max(),
    )


# ─────────────────────────────────────────────────────────────────
# Core vectorized feature builder  (§5)
# ─────────────────────────────────────────────────────────────────

def build_feature_matrix(
    pivot_data: PivotData,
    target_timestamps: List[pd.Timestamp] | pd.DatetimeIndex,
    location_keys: List[str],
    horizons_h: np.ndarray | None = None,
) -> np.ndarray:
    """
    Compute the 11-feature matrix for a batch of (target_timestamp,
    location_key) pairs.

    Returns:
        np.ndarray of shape (n_samples, 11), dtype float32.

    Algorithm — fully vectorized, no Python loop over samples:
    1. Map each target_timestamp → row index in the pivot matrix.
    2. Map each location_key     → col index in the pivot matrix.
    3. For each of the 11 offsets (in hours), subtract from the row
       indices and do ONE numpy fancy-index lookup.
    4. Any lookup that falls before the panel start (< row 0) is cold-start
       → fill with 0 (do NOT drop the row).
    5. Any unknown location_key or timestamp → all 11 features = 0.
    """
    n = len(target_timestamps)
    assert len(location_keys) == n, "target_timestamps and location_keys must be same length"

    target_timestamps = pd.to_datetime(target_timestamps)

    # ── Step 1 & 2: Convert to integer positions ─────────────────
    # Arithmetic row position: compute hours since panel_start so that
    # timestamps BEYOND the panel end still get a valid virtual row index.
    # Lookback offsets (t-1h, t-24h, etc.) can then point back into the
    # matrix even when the target itself is outside the stored range.
    # This fixes the bug where e.g. 2024-04-08T18:00 (1 hour past the
    # panel end at 17:00) would return -1 from the dictionary lookup,
    # zeroing out all features and making predictions meaningless.
    panel_start_ns = pivot_data.panel_start.value  # nanoseconds
    one_hour_ns = int(pd.Timedelta(hours=1).value)
    row_pos = np.array(
        [
            int((ts.value - panel_start_ns) // one_hour_ns)
            if not pd.isna(ts) else -1
            for ts in target_timestamps
        ],
        dtype=np.int64,
    )
    n_rows = pivot_data.matrix.shape[0]

    col_pos = np.array(
        [pivot_data.loc_to_pos.get(loc, -1) for loc in location_keys],
        dtype=np.int32,
    )

    if horizons_h is None:
        horizons_h = np.zeros(n, dtype=np.int64)

    effective_row_pos = row_pos - horizons_h

    # ── Step 3–5: One numpy lookup per offset ────────────────────
    features = np.zeros((n, len(_OFFSETS_H)), dtype=np.float32)

    for feat_idx, offset in enumerate(_OFFSETS_H):
        lookup_rows = effective_row_pos - offset          # can be negative (cold start)

        # Valid: col_pos >= 0 (loc found),
        #        lookup_rows >= 0 (not before panel start),
        #        lookup_rows < n_rows (within stored matrix bounds)
        valid = (lookup_rows >= 0) & (lookup_rows < n_rows) & (col_pos >= 0)

        if valid.any():
            features[valid, feat_idx] = pivot_data.matrix[
                lookup_rows[valid],
                col_pos[valid],
            ]
        # invalid indices remain 0 (cold start or unknown key)

    return features


def build_feature_df(
    pivot_data: PivotData,
    target_timestamps: List[pd.Timestamp] | pd.DatetimeIndex,
    location_keys: List[str],
    horizons_h: np.ndarray | None = None,
) -> pd.DataFrame:
    """Convenience wrapper: returns a named DataFrame instead of raw ndarray."""
    mat = build_feature_matrix(pivot_data, target_timestamps, location_keys, horizons_h)
    return pd.DataFrame(mat, columns=FEATURE_NAMES)


# ─────────────────────────────────────────────────────────────────
# Context features (LightGBM extras — §5 optional context)
# ─────────────────────────────────────────────────────────────────

def add_context_features(
    feat_df: pd.DataFrame,
    target_timestamps: List[pd.Timestamp] | pd.DatetimeIndex,
    horizons_h: np.ndarray | None = None,
) -> pd.DataFrame:
    """
    Append hour, weekday, is_weekend columns to the feature DataFrame.
    These are NOT part of the baseline model (which must stay explainable
    via the 11 lookback numbers alone), but are fed to LightGBM as extra
    context.  See §5 of the spec.
    """
    ts = pd.to_datetime(target_timestamps)
    out = feat_df.copy()
    out["hour"]       = ts.hour.astype(np.int8)
    out["weekday"]    = ts.weekday.astype(np.int8)      # property, not callable
    out["is_weekend"] = (out["weekday"] >= 5).astype(np.int8)
    out["horizon"]    = horizons_h if horizons_h is not None else 0
    return out


# ─────────────────────────────────────────────────────────────────
# Training example generator  (§6)
# ─────────────────────────────────────────────────────────────────

def generate_training_examples(
    panel_df: pd.DataFrame,
    pivot_data: PivotData,
    min_history_days: int = MIN_HISTORY_DAYS,
    label_column_name: str = "violation_count",
) -> pd.DataFrame:
    """
    Generate one training example per (location_key, target_timestamp)
    pair, skipping the first `min_history_days` of the dataset to avoid
    cold-start examples where most lookback features are 0.

    §6 cutoff rationale:
    MIN_HISTORY_DAYS = 21 ensures the same_hour_wd_w3 feature (21-day
    lookback) is non-trivially zero for at least some examples.

    Returns a DataFrame with columns:
        location_key, target_timestamp,
        [11 feature columns],
        hour, weekday, is_weekend,  (context — for LightGBM)
        <label_column_name>         (the label)

    Vectorised: one build_feature_matrix call over ALL examples at once.
    """
    cutoff_start = pivot_data.panel_start + pd.Timedelta(days=min_history_days)
    log.info(
        "Generating training examples after %s (skipping first %d days)",
        cutoff_start, min_history_days,
    )

    # Filter panel to rows >= cutoff_start (labels only; features look backwards)
    eligible = panel_df[panel_df["timestamp"] >= cutoff_start].copy()
    log.info("Eligible (location, timestamp) pairs: %d", len(eligible))

    target_timestamps = eligible["timestamp"].tolist()
    location_keys     = eligible["location_key"].tolist()
    labels            = eligible["violation_count"].values

    # Generate random horizons between 0 and 168 (1 week)
    np.random.seed(42)
    horizons_h = np.random.randint(0, 169, size=len(target_timestamps)).astype(np.int64)

    # Build 11-feature matrix in one vectorised call
    feat_mat = build_feature_matrix(pivot_data, target_timestamps, location_keys, horizons_h)

    # Assemble output DataFrame
    result = pd.DataFrame(feat_mat, columns=FEATURE_NAMES)
    result["location_key"]       = location_keys
    result["target_timestamp"]   = pd.to_datetime(target_timestamps)
    if label_column_name == "severity_score":
        result[label_column_name] = labels.astype(np.float32)
    else:
        result[label_column_name] = labels.astype(np.int32)

    # Append context features for LightGBM
    ts_arr = pd.to_datetime(target_timestamps)
    result["hour"]       = ts_arr.hour.astype(np.int8)
    result["weekday"]    = ts_arr.weekday.astype(np.int8)   # property, not callable
    result["is_weekend"] = (result["weekday"] >= 5).astype(np.int8)
    result["horizon"]    = horizons_h.astype(np.int32)

    log.info(
        "Training examples generated: %d rows  "
        "(label mean=%.4f, label>0: %.1f%%)",
        len(result),
        labels.mean(),
        100.0 * (labels > 0).mean(),
    )
    return result
