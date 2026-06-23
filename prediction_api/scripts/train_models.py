"""
train_models.py — End-to-end training pipeline.

Usage:
  python scripts/train_models.py
  python scripts/train_models.py --zero-sample-rate 0.1  # faster (10% of zeros)
  python scripts/train_models.py --no-lgbm               # baseline only

What this script does:
  1. Load the dense panel parquet (build_canonical_timeseries.py must run first).
  2. Build the pivot matrix for feature extraction.
  3. Generate all training examples (location × hour after MIN_HISTORY_DAYS cutoff).
     Optionally subsample zero-violation rows to reduce memory/time.
  4. Sort by target_timestamp — temporal split (NEVER shuffle):
       train  : everything before (panel_end - TEST_DAYS - VAL_DAYS)
       val    : last VAL_DAYS  before test  (LightGBM early-stopping)
       test   : last TEST_DAYS of the panel (held-out evaluation)
  5. Train & save Baseline (just write config JSON — no fitting needed).
  6. Train & save LightGBM (Poisson, early-stop on val).
  7. Compute all three predictions on the test set.
  8. Evaluate precision@5 and print the comparison table.

Key constraint (§7): Never use train_test_split(shuffle=True).
Shuffling leaks future information into training and makes every metric
meaningless on time-series data.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import (
    PARQUET_PATH, PARQUET_SEVERITY_PATH,
    TEST_DAYS, VAL_DAYS, MIN_HISTORY_DAYS,
    ALL_LGBM_FEATURES, FEATURE_NAMES,
    LGBM_SEVERITY_MODEL, BASELINE_SEVERITY_JSON,
    ROAD_CLASS_LOOKUP, DEFAULT_ROAD_WEIGHT,
)
from app.services.data_pipeline import load_panel
from app.services.feature_engineering import (
    build_pivot_matrix, generate_training_examples,
)
from app.services.model_baseline import (
    naive_predict, baseline_predict, save_baseline_config,
)
from app.services.model_lightgbm import LGBMPredictor
from app.services.evaluation import evaluate_all, print_eval_table

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train baseline + LightGBM and evaluate.")
    p.add_argument(
        "--target", choices=["count", "severity"], default="count",
        help=(
            "Which target to train on. "
            "'count' = violation_count (Part 1, Poisson objective). "
            "'severity' = severity_score (Part 2, Tweedie objective). "
            "Default: count"
        ),
    )
    p.add_argument(
        "--zero-sample-rate", type=float, default=1.0,
        metavar="RATE",
        help=(
            "Fraction of zero-violation rows to keep for training "
            "(1.0 = keep all, 0.1 = 10%% of zeros — much faster). "
            "Non-zero rows are always kept. Default: 1.0"
        ),
    )
    p.add_argument(
        "--no-lgbm", action="store_true",
        help="Skip LightGBM training (run baseline only).",
    )
    p.add_argument(
        "--panel", type=Path, default=None,
        help="Path to dense panel parquet (overrides --target default path).",
    )
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────
# Temporal split — §7
# ─────────────────────────────────────────────────────────────────

def temporal_split(
    examples: pd.DataFrame,
    test_days: int = TEST_DAYS,
    val_days:  int = VAL_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Sort all examples by target_timestamp, then cut off:
      test : last test_days
      val  : val_days immediately before test
      train: everything else

    IMPORTANT: sort is done here so callers cannot accidentally shuffle first.
    """
    examples = examples.sort_values("target_timestamp").reset_index(drop=True)

    ts_max   = examples["target_timestamp"].max()
    test_cut = ts_max - pd.Timedelta(days=test_days)
    val_cut  = test_cut - pd.Timedelta(days=val_days)

    test  = examples[examples["target_timestamp"] >  test_cut]
    val   = examples[(examples["target_timestamp"] > val_cut) &
                     (examples["target_timestamp"] <= test_cut)]
    train = examples[examples["target_timestamp"] <= val_cut]

    log.info(
        "Temporal split:  train=%d  val=%d  test=%d rows",
        len(train), len(val), len(test),
    )
    log.info(
        "  train: %s -> %s",
        train["target_timestamp"].min(), train["target_timestamp"].max(),
    )
    log.info(
        "  val  : %s -> %s",
        val["target_timestamp"].min(),   val["target_timestamp"].max(),
    )
    log.info(
        "  test : %s -> %s",
        test["target_timestamp"].min(),  test["target_timestamp"].max(),
    )
    return train, val, test


# ─────────────────────────────────────────────────────────────────
# Subsample zero-violation rows (optional, for speed)
# ─────────────────────────────────────────────────────────────────

def subsample_zeros(df: pd.DataFrame, rate: float, rng_seed: int = 42) -> pd.DataFrame:
    """
    Keep all rows with violation_count > 0, and a random `rate` fraction
    of zero rows.  Used only on the TRAIN set — val and test are kept
    complete so evaluation is not biased.
    """
    if rate >= 1.0:
        return df
    nonzero = df[df["violation_count"] > 0]
    zeros   = df[df["violation_count"] == 0].sample(frac=rate, random_state=rng_seed)
    result  = pd.concat([nonzero, zeros]).sort_values("target_timestamp")
    log.info(
        "After zero subsampling (rate=%.2f): %d -> %d train rows",
        rate, len(df), len(result),
    )
    return result


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    t_total = time.time()

    # Resolve paths and params based on --target
    is_severity = args.target == "severity"
    if args.panel is None:
        panel_path = PARQUET_SEVERITY_PATH if is_severity else PARQUET_PATH
    else:
        panel_path = args.panel

    # Import severity-specific config only when needed
    if is_severity:
        from app.config import LGBM_SEVERITY_PARAMS, BASELINE_SEVERITY_JSON
        lgbm_params   = LGBM_SEVERITY_PARAMS
        baseline_path = BASELINE_SEVERITY_JSON
        model_suffix  = "_severity"
    else:
        from app.config import LGBM_PARAMS
        lgbm_params   = LGBM_PARAMS
        baseline_path = None  # save_baseline_config() uses its own default
        model_suffix  = ""

    log.info("=" * 65)
    log.info("TRAIN MODELS  [target=%s]", args.target)
    log.info("  Panel           : %s", panel_path)
    log.info("  Zero sample rate: %.2f", args.zero_sample_rate)
    log.info("  Skip LightGBM   : %s", args.no_lgbm)
    log.info("=" * 65)

    # ── 1. Load panel ────────────────────────────────────────────
    panel = load_panel(panel_path)

    # ── 2. Build pivot matrix ────────────────────────────────────
    log.info("Building pivot matrix...")
    t0 = time.time()
    pivot_data = build_pivot_matrix(panel)
    log.info("  Pivot ready in %.1fs", time.time() - t0)

    # ── 2b. Load OSM road weights (optional) ─────────────────────
    # road_weight_osm is a static per-location feature (0.15=motorway → 1.0=footway).
    # If the lookup file doesn't exist, all examples get DEFAULT_ROAD_WEIGHT and
    # the feature still trains — it just won't vary across locations.
    road_weights: dict[str, float] = {}
    if ROAD_CLASS_LOOKUP.exists():
        with open(ROAD_CLASS_LOOKUP, encoding="utf-8") as f:
            import json as _json
            lookup = _json.load(f)
        road_weights = {k: v["road_weight"] for k, v in lookup.items()}
        matched = sum(1 for k in pivot_data.loc_to_pos if k in road_weights)
        log.info(
            "  OSM road weights loaded: %d total, %d / %d pivot locs matched (%.1f%%)",
            len(road_weights), matched, len(pivot_data.loc_to_pos),
            100 * matched / max(len(pivot_data.loc_to_pos), 1),
        )
    else:
        log.warning(
            "  road_class_lookup.json not found — road_weight_osm will be %.2f for all locs",
            DEFAULT_ROAD_WEIGHT,
        )

    # ── 3. Generate training examples ────────────────────────────
    log.info("Generating training examples (MIN_HISTORY_DAYS=%d)...", MIN_HISTORY_DAYS)
    t0 = time.time()
    examples = generate_training_examples(
        panel, pivot_data, MIN_HISTORY_DAYS,
        road_weights=road_weights if road_weights else None,
    )
    log.info("  %d examples in %.1fs", len(examples), time.time() - t0)

    del panel  # free memory

    # ── 4. Temporal split ────────────────────────────────────────
    train_df, val_df, test_df = temporal_split(examples, TEST_DAYS, VAL_DAYS)

    # Optionally subsample train zeros (val & test stay complete)
    train_df = subsample_zeros(train_df, args.zero_sample_rate)

    # ── 5. Baseline — save config, no fitting needed ───────────────────
    log.info("Saving baseline config (target=%s)...", args.target)
    if baseline_path is not None:
        save_baseline_config(path=baseline_path)
    else:
        save_baseline_config()  # uses default BASELINE_JSON from config
    log.info("  Baseline config saved.")

    # ── 6. LightGBM training ───────────────────────────────────────
    lgbm_model = None
    if not args.no_lgbm:
        log.info("Training LightGBM (objective=%s)...", lgbm_params["objective"])

        X_train = train_df[ALL_LGBM_FEATURES].values
        y_train = train_df["violation_count"].values.astype(np.float32)
        X_val   = val_df[ALL_LGBM_FEATURES].values
        y_val   = val_df["violation_count"].values.astype(np.float32)

        # For severity target, upweight non-zero rows so the model doesn't
        # ignore the rare severity events drowned out by 99.6% zeros.
        sample_weights = None
        if is_severity:
            from app.config import SEVERITY_NONZERO_WEIGHT
            w = np.ones(len(y_train), dtype=np.float32)
            w[y_train > 0] = SEVERITY_NONZERO_WEIGHT
            sample_weights = w
            log.info(
                "  Severity sample weights: %d non-zero (%.1f×) + %d zero (1×)",
                (y_train > 0).sum(), SEVERITY_NONZERO_WEIGHT, (y_train == 0).sum(),
            )

        t0 = time.time()
        lgbm_model = LGBMPredictor(lgbm_params=lgbm_params)
        lgbm_model.train(
            X_train, y_train,
            X_val,   y_val,
            feature_names=ALL_LGBM_FEATURES,
            sample_weight=sample_weights,
        )
        log.info("  LightGBM trained in %.1fs", time.time() - t0)

        # Save to target-specific path
        from app.config import MODELS_DIR
        save_path = MODELS_DIR / f"lightgbm_model{model_suffix}.txt"
        lgbm_model.save(path=save_path)
        log.info("  Model saved → %s", save_path)

        fi = lgbm_model.feature_importance().head(10)
        print("\nTop-10 features by gain:")
        print(fi.to_string(index=False))

    # ── 7. Compute predictions on test set ───────────────────────
    log.info("Computing test-set predictions...")

    X_test_feats = test_df[FEATURE_NAMES].values    # 11 core features
    X_test_all   = test_df[ALL_LGBM_FEATURES].values  # 14 (incl. context)

    test_df = test_df.copy()
    test_df["naive_prediction"]    = naive_predict(X_test_feats)
    test_df["baseline_prediction"] = baseline_predict(X_test_feats)

    if lgbm_model is not None:
        test_df["lightgbm_prediction"] = lgbm_model.predict(X_test_all)
    else:
        # If LightGBM was skipped, fill with NaN so evaluate_all can skip it
        test_df["lightgbm_prediction"] = np.nan

    # ── 8. Evaluate precision@5 ──────────────────────────────────
    log.info("Evaluating precision@5...")
    pred_cols = ["naive_prediction", "baseline_prediction"]
    if lgbm_model is not None:
        pred_cols.append("lightgbm_prediction")

    summary = evaluate_all(test_df, pred_cols=pred_cols, k=5)
    print_eval_table(summary, k=5)

    # Manual QA gate (§13): flag if LightGBM doesn't beat baseline
    if lgbm_model is not None:
        p_lgbm     = summary.loc[summary["model"] == "lightgbm",     "precision_at_5"].values
        p_baseline = summary.loc[summary["model"] == "baseline",     "precision_at_5"].values
        p_naive    = summary.loc[summary["model"] == "naive",        "precision_at_5"].values
        if len(p_lgbm) and len(p_baseline):
            if p_lgbm[0] < p_baseline[0]:
                log.warning(
                    "QA ALERT: LightGBM (%.4f) < baseline (%.4f). "
                    "Investigate before shipping — possible data leak, "
                    "overfitting, or insufficient training data.",
                    p_lgbm[0], p_baseline[0],
                )
            else:
                log.info(
                    "QA PASS: LightGBM (%.4f) >= baseline (%.4f) >= naive (%.4f)",
                    p_lgbm[0],
                    p_baseline[0] if len(p_baseline) else float("nan"),
                    p_naive[0]    if len(p_naive)    else float("nan"),
                )

    log.info("Total time: %.1fs", time.time() - t_total)
    log.info("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
