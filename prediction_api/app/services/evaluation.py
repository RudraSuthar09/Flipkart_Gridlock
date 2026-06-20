"""
evaluation.py — Precision@5 backtesting for naive, baseline, LightGBM.

§10 of the spec:
  For every distinct target_timestamp in the test set:
    1. True top-5: locations ranked by actual violation_count.
    2. Predicted top-5: locations ranked by each model's prediction.
    3. precision@5 = |true_top5 ∩ predicted_top5| / 5
    4. Average across all test timestamps → one number per model.

  Final table printed by train_models.py:
    model        precision@5 (avg over N test hours)
    naive        0.21
    baseline     0.34
    lightgbm     0.47
"""
from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Core metric
# ─────────────────────────────────────────────────────────────────

def precision_at_k(
    true_top_k: List[str],
    pred_top_k: List[str],
    k: int = 5,
) -> float:
    """
    |true_top_k ∩ pred_top_k| / k

    Both lists should already be ranked (only the set membership matters
    for precision@k, not internal ordering within the top-k).
    """
    true_set = set(true_top_k[:k])
    pred_set = set(pred_top_k[:k])
    return len(true_set & pred_set) / k


# ─────────────────────────────────────────────────────────────────
# Top-k extractor
# ─────────────────────────────────────────────────────────────────

def top_k_locations(
    scores: pd.Series,       # index = location_key, values = score/count
    k: int = 5,
) -> List[str]:
    """Return the top-k location_keys by score, descending."""
    return scores.nlargest(k).index.tolist()


# ─────────────────────────────────────────────────────────────────
# Per-timestamp precision
# ─────────────────────────────────────────────────────────────────

def evaluate_timestamp(
    group: pd.DataFrame,
    pred_cols: List[str],
    k: int = 5,
) -> Dict[str, float]:
    """
    For a single target_timestamp slice of the test DataFrame:
    - group has columns: location_key, violation_count, <pred_cols...>
    - Returns a dict of precision@k per model.
    If there are fewer than k locations with any count, we still compute
    the metric (it will naturally be lower due to a small denominator k).
    """
    true_top = top_k_locations(
        group.set_index("location_key")["violation_count"], k=k
    )
    results = {}
    for col in pred_cols:
        pred_top = top_k_locations(
            group.set_index("location_key")[col], k=k
        )
        results[col] = precision_at_k(true_top, pred_top, k=k)
    return results


# ─────────────────────────────────────────────────────────────────
# Full test-set evaluation
# ─────────────────────────────────────────────────────────────────

def evaluate_all(
    test_df: pd.DataFrame,
    pred_cols: List[str] | None = None,
    k: int = 5,
) -> pd.DataFrame:
    """
    Compute per-timestamp and then average precision@k for all models.

    Parameters
    ----------
    test_df : DataFrame with columns:
        location_key, target_timestamp, violation_count,
        naive_prediction, baseline_prediction, lightgbm_prediction
    pred_cols : list of column names to evaluate (default: all three)
    k : top-k threshold (default 5, per spec)

    Returns
    -------
    summary_df : DataFrame with columns [model, precision_at_k, n_timestamps]
    """
    if pred_cols is None:
        pred_cols = ["naive_prediction", "baseline_prediction", "lightgbm_prediction"]

    # Verify all required columns exist
    missing = [c for c in ["location_key", "target_timestamp", "violation_count"] + pred_cols
               if c not in test_df.columns]
    if missing:
        raise ValueError(f"test_df missing columns: {missing}")

    timestamps = test_df["target_timestamp"].unique()
    log.info("Evaluating precision@%d over %d test timestamps...", k, len(timestamps))

    per_ts_records = []
    for ts in timestamps:
        group = test_df[test_df["target_timestamp"] == ts]
        if len(group) < k:
            # Not enough locations at this hour to fill the top-k list
            # (e.g. a very rare time slot). Skip to avoid misleading metrics.
            continue
        row = evaluate_timestamp(group, pred_cols, k=k)
        row["target_timestamp"] = ts
        per_ts_records.append(row)

    if not per_ts_records:
        log.warning("No valid timestamps found for evaluation!")
        return pd.DataFrame(columns=["model", f"precision_at_{k}", "n_timestamps"])

    per_ts_df = pd.DataFrame(per_ts_records)
    n_valid   = len(per_ts_df)

    # Average across timestamps
    summary_rows = []
    for col in pred_cols:
        mean_p = per_ts_df[col].mean()
        summary_rows.append({
            "model":              col.replace("_prediction", ""),
            f"precision_at_{k}": round(mean_p, 4),
            "n_timestamps":       n_valid,
        })

    summary_df = pd.DataFrame(summary_rows)
    return summary_df


# ─────────────────────────────────────────────────────────────────
# Pretty-print the evaluation table
# ─────────────────────────────────────────────────────────────────

def print_eval_table(summary_df: pd.DataFrame, k: int = 5) -> None:
    """Print the precision@k comparison table to stdout (§10 format)."""
    col = f"precision_at_{k}"
    n   = summary_df["n_timestamps"].iloc[0] if len(summary_df) else 0

    print(f"\n{'='*55}")
    print(f"  Precision@{k} — averaged over {n:,} test timestamps")
    print(f"{'='*55}")
    print(f"  {'model':<22}  {f'precision@{k}':>12}")
    print(f"  {'-'*22}  {'-'*12}")
    for _, row in summary_df.iterrows():
        marker = "  <-- our model" if row["model"] == "lightgbm" else ""
        print(f"  {row['model']:<22}  {row[col]:>12.4f}{marker}")
    print(f"{'='*55}\n")
