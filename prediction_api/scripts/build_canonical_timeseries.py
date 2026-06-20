"""
build_canonical_timeseries.py — CLI script to convert the raw feature CSV
into the dense per-location hourly parquet panel.

Usage:
  # Part 1 — violation count (default)
  python scripts/build_canonical_timeseries.py
  python scripts/build_canonical_timeseries.py --target count

  # Part 2 — severity score
  python scripts/build_canonical_timeseries.py --target severity

  # Custom paths
  python scripts/build_canonical_timeseries.py --csv path/to/other.csv
  python scripts/build_canonical_timeseries.py --out path/to/output.parquet

Exit codes: 0 = success, 1 = error (see stderr for details).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Allow running from both the project root and the scripts/ directory ────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import RAW_CSV, PARQUET_PATH, PARQUET_SEVERITY_PATH
from app.services.data_pipeline import (
    load_and_validate,
    load_severity_and_validate,
    build_location_master,
    aggregate_to_grain,
    get_date_range,
    densify,
    save_panel,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the canonical dense hourly panel from the raw feature CSV."
    )
    parser.add_argument(
        "--target",
        choices=["count", "severity"],
        default="count",
        help=(
            "Which target to densify. "
            "'count' = violation_count (Part 1, default). "
            "'severity' = severity_score (Part 2, Tweedie-ready). "
        ),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=RAW_CSV,
        help=f"Path to input CSV (default: {RAW_CSV})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Path to output parquet. "
            "Defaults to canonical_timeseries.parquet for --target count, "
            "or canonical_severity_timeseries.parquet for --target severity."
        ),
    )
    args = parser.parse_args()

    # Resolve output path
    is_severity = args.target == "severity"
    if args.out is None:
        out_path = PARQUET_SEVERITY_PATH if is_severity else PARQUET_PATH
    else:
        out_path = args.out

    value_column = "severity_score" if is_severity else "violation_count"

    t0 = time.time()
    log.info("=" * 60)
    log.info("BUILD CANONICAL TIMESERIES  [target=%s]", args.target)
    log.info("  Input : %s", args.csv)
    log.info("  Output: %s", out_path)
    log.info("  Value : %s", value_column)
    log.info("=" * 60)

    # ── Step 1: Load & validate ──────────────────────────────────
    if is_severity:
        df = load_severity_and_validate(args.csv)
    else:
        df = load_and_validate(args.csv)

    # ── Step 2: Location master ──────────────────────────────────
    location_master = build_location_master(df)
    log.info(
        "Location master: %d unique junctions/grid cells",
        len(location_master),
    )

    # ── Step 3: Aggregate to (location_key, hour_slot) grain ────
    agg = aggregate_to_grain(df, value_column=value_column)

    # ── Step 4: Date range ───────────────────────────────────────
    min_ts, max_ts = get_date_range(agg)
    span_days = (max_ts - min_ts).days
    log.info("Dataset span: %d days", span_days)

    # ── Step 5: Densify ──────────────────────────────────────────
    panel = densify(agg, min_ts, max_ts, value_column=value_column)

    # ── Verification ─────────────────────────────────────────────
    n_loc     = panel["location_key"].nunique()
    n_hours   = panel["timestamp"].nunique()
    expected  = n_loc * n_hours
    actual    = len(panel)
    assert actual == expected, (
        f"Dense panel incomplete: expected {expected} rows, got {actual}. "
        "This is a bug in densify()."
    )
    zero_frac = (panel["violation_count"] == 0).mean()
    log.info(
        "Verification OK — %d rows = %d locations × %d hours  |  "
        "%.1f%% zero hours (expected: high, data is sparse)",
        actual, n_loc, n_hours, 100.0 * zero_frac,
    )

    # ── Save ─────────────────────────────────────────────────────
    save_panel(panel, out_path)

    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info("DONE in %.1f s", elapsed)
    log.info("=" * 60)

    # Print quick summary to stdout so CI can capture it
    print(f"\nPanel written to: {out_path}")
    print(f"  Target    : {args.target}")
    print(f"  Value col : {value_column}")
    print(f"  Locations : {n_loc:,}")
    print(f"  Hours     : {n_hours:,}")
    print(f"  Total rows: {actual:,}")
    print(f"  Zero rows : {zero_frac*100:.1f}%  (sparse — expected)")
    print(f"  Date range: {min_ts} -> {max_ts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
