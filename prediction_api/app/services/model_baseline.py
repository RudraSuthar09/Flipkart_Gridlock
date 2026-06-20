"""
model_baseline.py — Recency-weighted sum baseline (§8 of spec).

Formula:
  baseline_score = (
      sum(HOUR_WEIGHTS[i]  * recent_h[i]       for i in 0..3) +
      sum(DAY_WEIGHTS[i]   * same_hour_d[i]    for i in 0..3) +
      sum(WEEK_WEIGHTS[i]  * same_hour_wd_w[i] for i in 0..2)
  ) / WEIGHT_SUM

Output is on the same scale as violation_count (it's a normalized weighted
average of prior counts), so it's directly comparable to LightGBM output.

Separately, naive_prediction = same_hour_d1 (literally "same hour
yesterday") — the simplest possible baseline, used as the UI toggle's
"naive" option.  NOT the same as baseline_prediction.

No "training" is needed — the weights are config-driven constants.
Save/load just persists the weight arrays to JSON so the exact weights
used during a run are reproducible.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from app.config import (
    HOUR_WEIGHTS, DAY_WEIGHTS, WEEK_WEIGHTS, WEIGHT_SUM,
    BASELINE_JSON, FEATURE_NAMES,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Prediction functions — pure, no state
# ─────────────────────────────────────────────────────────────────

def naive_predict(features: Union[pd.DataFrame, np.ndarray]) -> np.ndarray:
    """
    Naive prediction: same_hour_d1 (yesterday's same-hour count).
    This is feature index 4 in the 11-feature vector.
    Used as the 'naive' comparison in the frontend toggle.
    """
    if isinstance(features, pd.DataFrame):
        return features["same_hour_d1"].values.astype(np.float32)
    # ndarray: same_hour_d1 is column index 4
    return features[:, 4].astype(np.float32)


def baseline_predict(features: Union[pd.DataFrame, np.ndarray]) -> np.ndarray:
    """
    Recency-weighted baseline prediction (§8).

    Works on both a named DataFrame (production path) and a raw ndarray
    (training path where column names are in FEATURE_NAMES order).

    All weights come from config.py — change them there, not here.
    """
    if isinstance(features, pd.DataFrame):
        arr = features[FEATURE_NAMES].values.astype(np.float32)
    else:
        arr = features.astype(np.float32)

    # Split columns by feature group
    recent_h   = arr[:, 0:4]    # recent_h1..h4
    same_day   = arr[:, 4:8]    # same_hour_d1..d4
    same_week  = arr[:, 8:11]   # same_hour_wd_w1..w3

    hw = np.array(HOUR_WEIGHTS,  dtype=np.float32)   # shape (4,)
    dw = np.array(DAY_WEIGHTS,   dtype=np.float32)   # shape (4,)
    ww = np.array(WEEK_WEIGHTS,  dtype=np.float32)   # shape (3,)

    # Matrix-vector dot products → one score per row
    score = (
        recent_h  @ hw +
        same_day  @ dw +
        same_week @ ww
    ) / WEIGHT_SUM

    return score.astype(np.float32)


# ─────────────────────────────────────────────────────────────────
# Persist the weights used (for reproducibility)
# ─────────────────────────────────────────────────────────────────

def save_baseline_config(path: Path = BASELINE_JSON) -> None:
    """
    Save the weight arrays to JSON.  No 'model parameters' to store
    beyond the weights themselves — this is purely for auditability.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "hour_weights":  HOUR_WEIGHTS,
        "day_weights":   DAY_WEIGHTS,
        "week_weights":  WEEK_WEIGHTS,
        "weight_sum":    WEIGHT_SUM,
        "feature_names": FEATURE_NAMES,
        "description": (
            "Recency-weighted sum baseline.  "
            "baseline_score = dot(weights, features) / weight_sum.  "
            "naive_prediction = same_hour_d1 (feature index 4)."
        ),
    }
    with open(path, "w") as fh:
        json.dump(config, fh, indent=2)
    log.info("Baseline config saved -> %s", path)


def load_baseline_config(path: Path = BASELINE_JSON) -> dict:
    """Load and return the baseline config JSON (for inspection)."""
    with open(path) as fh:
        return json.load(fh)
