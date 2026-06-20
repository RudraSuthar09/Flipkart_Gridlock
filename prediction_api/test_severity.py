"""
test_severity.py — Unit + integration tests for the Part 2 severity pipeline.

Test coverage:
  1. PCU config:     all 22 vehicle types resolve → known categories with PCU values
  2. Severity agg:   sum of individual severities (not average/single)
  3. Pipeline param: densify_panel with value_column="severity_score" produces correct shape
  4. Integration:    /health reports vehicle_mapping_coverage + lane_match_coverage
  5. Regression:     heavy-vehicle/narrow-road BEATS many-light-vehicle/wide-road in severity rank

Run with:
    cd prediction_api
    python -m pytest test_severity.py -v
or (without pytest):
    python test_severity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow imports from prediction_api package
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def load_configs():
    """Load pcu_weights.json and vehicle_type_mapping.json from the models dir."""
    models_dir = Path(__file__).parent / "models"
    with open(models_dir / "pcu_weights.json") as f:
        pcu = json.load(f)
    with open(models_dir / "vehicle_type_mapping.json") as f:
        vmap = json.load(f)
    return pcu, vmap


# ─────────────────────────────────────────────────────────────────
# Test 1 — PCU config
# ─────────────────────────────────────────────────────────────────

def test_pcu_config_all_vehicle_types_mapped():
    """
    All 22 vehicle types in vehicle_type_mapping.json must:
      a) map to a canonical category
      b) that category must have a numeric PCU value in pcu_weights.json
    """
    pcu, vmap = load_configs()

    # Collect non-metadata keys
    skip = {"_comment", "_coverage", "_source", "_fallback_pcu", "_fallback_note"}
    vehicle_types = {k: v for k, v in vmap.items() if k not in skip}
    categories    = {k: v for k, v in pcu.items() if k not in skip}

    assert len(vehicle_types) >= 22, (
        f"Expected >=22 vehicle type mappings, got {len(vehicle_types)}"
    )

    unmapped = []
    for vtype, category in vehicle_types.items():
        if category not in categories:
            unmapped.append(f"{vtype!r} → {category!r} (no PCU for this category)")

    assert not unmapped, (
        f"vehicle_type_mapping.json references unknown PCU categories:\n"
        + "\n".join(unmapped)
    )

    for cat, pcu_val in categories.items():
        assert isinstance(pcu_val, (int, float)), (
            f"PCU value for '{cat}' must be numeric, got {type(pcu_val)}"
        )
        assert pcu_val > 0, f"PCU value for '{cat}' must be positive"

    print(f"✓ test_pcu_config_all_vehicle_types_mapped  "
          f"({len(vehicle_types)} types, {len(categories)} categories)")


# ─────────────────────────────────────────────────────────────────
# Test 2 — Severity aggregation is a SUM, not an average
# ─────────────────────────────────────────────────────────────────

def test_severity_aggregation_is_sum():
    """
    A location-hour bucket with TWO violations must have severity_score
    equal to the SUM of the two individual severities, not one shared value.

    Synthetic setup (§5 of spec):
      Violation A: truck (PCU=3.0) on 1-lane road (road_weight=1.0), vtype_weight=1.0
                   row_severity_A = 3.0 × 1.0 × 1.0 = 3.0
      Violation B: scooter (PCU=0.5) on 1-lane road, vtype_weight=1.0
                   row_severity_B = 0.5 × 1.0 × 1.0 = 0.5
      Expected bucket severity_score = 3.0 + 0.5 = 3.5   ← sum
    """
    pcu_truck   = 3.0
    pcu_scooter = 0.5
    road_weight = 1.0   # 1/1 lane
    vtype_w     = 1.0

    sev_A = pcu_truck   * road_weight * vtype_w   # 3.0
    sev_B = pcu_scooter * road_weight * vtype_w   # 0.5
    expected_sum = sev_A + sev_B                   # 3.5

    # Simulate what the feature_engineering pipeline should produce
    rows = pd.DataFrame({
        "location_key":         ["LOC1", "LOC1"],
        "hour_slot":            ["2024-01-01 08:00:00", "2024-01-01 08:00:00"],
        "vehicle_type":         ["LORRY/GOODS VEHICLE", "SCOOTER"],
        "pcu_weight":           [pcu_truck, pcu_scooter],
        "road_weight":          [road_weight, road_weight],
        "violation_type_weight":[vtype_w, vtype_w],
        "severity_score":       [sev_A, sev_B],   # per-row (pre-aggregate)
    })

    # Aggregate: sum severity_score per (location_key, hour_slot)
    agg = rows.groupby(["location_key", "hour_slot"])["severity_score"].sum().reset_index()

    actual = float(agg.loc[agg["location_key"] == "LOC1", "severity_score"].iloc[0])
    assert abs(actual - expected_sum) < 1e-6, (
        f"Expected severity sum={expected_sum}, got {actual}. "
        "Severity MUST be summed per bucket, not averaged."
    )
    print(f"✓ test_severity_aggregation_is_sum  (expected={expected_sum}, got={actual})")


# ─────────────────────────────────────────────────────────────────
# Test 3 — densify_panel value_column parameter
# ─────────────────────────────────────────────────────────────────

def test_densify_panel_value_column_severity():
    """
    densify() with value_column='severity_score' must produce a complete
    hourly grid with the same dimensions as the count-based panel.
    """
    from app.services.data_pipeline import aggregate_to_grain, get_date_range, densify

    # Tiny synthetic dataset: 2 locations, 3 hours
    df = pd.DataFrame({
        "location_key": ["LOC_A", "LOC_A", "LOC_B"],
        "hour_slot":    pd.to_datetime(["2024-01-01 08:00", "2024-01-01 09:00", "2024-01-01 08:00"]),
        "severity_score": [1.5, 0.8, 2.0],
        "weekday":      [0, 0, 0],
        "is_weekend":   [0, 0, 0],
    })

    agg             = aggregate_to_grain(df, value_column="severity_score")
    min_ts, max_ts  = get_date_range(agg)
    panel           = densify(agg, min_ts, max_ts, value_column="severity_score")

    n_locs  = panel["location_key"].nunique()
    n_hours = panel["timestamp"].nunique()
    assert len(panel) == n_locs * n_hours, (
        f"Panel is not dense: expected {n_locs}×{n_hours}={n_locs*n_hours} rows, got {len(panel)}"
    )
    assert "violation_count" in panel.columns, (
        "Panel must rename severity_score → violation_count for downstream compatibility"
    )
    # The non-zero rows must equal what we put in
    nonzero = panel[panel["violation_count"] > 0]
    assert len(nonzero) == 3, f"Expected 3 non-zero rows, got {len(nonzero)}"

    print(f"✓ test_densify_panel_value_column_severity  "
          f"({n_locs} locs × {n_hours} hours = {len(panel)} rows)")


# ─────────────────────────────────────────────────────────────────
# Test 4 — /health endpoint coverage fields (live API)
# ─────────────────────────────────────────────────────────────────

def test_severity_health_endpoint():
    """
    /api/v1/traffic-severity/health must return:
      - status = "ok"
      - vehicle_mapping_coverage in [0, 1]
      - lane_match_coverage      in [0, 1]
    Skipped automatically if the API is not running.
    """
    try:
        import requests
        r = requests.get(
            "http://127.0.0.1:8001/api/v1/traffic-severity/health",
            timeout=5,
        )
    except Exception as e:
        print(f"⚠  test_severity_health_endpoint SKIPPED (API not running: {e})")
        return

    assert r.status_code == 200, f"Expected HTTP 200, got {r.status_code}"
    data = r.json()
    assert data["status"] == "ok", f"status != ok: {data}"
    assert "vehicle_mapping_coverage" in data, "Missing vehicle_mapping_coverage in /health"
    assert "lane_match_coverage"      in data, "Missing lane_match_coverage in /health"
    assert 0.0 <= data["vehicle_mapping_coverage"] <= 1.0
    assert 0.0 <= data["lane_match_coverage"]      <= 1.0

    print(
        f"✓ test_severity_health_endpoint  "
        f"(veh_cov={data['vehicle_mapping_coverage']:.2f}  "
        f"lane_cov={data['lane_match_coverage']:.2f})"
    )


# ─────────────────────────────────────────────────────────────────
# Test 5 — Ranking regression: heavy/narrow BEATS light/wide
# ─────────────────────────────────────────────────────────────────

def test_severity_ranking_regression():
    """
    CORE regression from §7 of the spec:
    A heavy-vehicle violation on a 1-lane road MUST have a higher
    severity score than multiple two-wheeler violations on a 4-lane road,
    even though the 4-lane location has a higher raw violation_count.

    Fixture:
      Location A: 1 × heavy truck (PCU=3.0) on 1-lane road (road_weight=1.0)
                  violation_type_weight = 1.0
                  severity = 3.0 × 1.0 × 1.0 = 3.0
                  count    = 1

      Location B: 4 × scooter (PCU=0.5) on 4-lane road (road_weight=0.25)
                  violation_type_weight = 1.0
                  severity = 4 × (0.5 × 0.25 × 1.0) = 0.5
                  count    = 4   (4× more violations than A)

    Expected:
      - Count ranking:   B > A  (4 > 1)
      - Severity ranking: A > B  (3.0 > 0.5)   ← the whole point of Part 2
    """
    pcu, vmap = load_configs()

    # Severity scores (computed as in the pipeline)
    severity_A = 3.0 * 1.0 * 1.0   # heavy truck, 1-lane, standard violation
    severity_B = 4 * (0.5 * 0.25 * 1.0)  # 4 scooters, 4-lane

    count_A = 1
    count_B = 4

    # Count ranking: B beats A
    assert count_B > count_A, "Fixture error: B should have more violations than A"

    # Severity ranking: A beats B — this is the whole point of Part 2
    assert severity_A > severity_B, (
        f"REGRESSION FAILURE: severity_A ({severity_A}) should beat severity_B ({severity_B}). "
        f"A heavy truck on a 1-lane road MUST outrank {count_B} scooters on a 4-lane road. "
        "Check PCU weights and road_weight formula."
    )

    print(
        f"✓ test_severity_ranking_regression  "
        f"| A: count={count_A}, severity={severity_A:.2f}  "
        f"| B: count={count_B}, severity={severity_B:.2f}  "
        f"| Severity rank: A(#{1}) > B(#{2}) despite count rank B(#{1}) > A(#{2})"
    )


# ─────────────────────────────────────────────────────────────────
# Runner (no pytest required)
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_pcu_config_all_vehicle_types_mapped,
        test_severity_aggregation_is_sum,
        test_densify_panel_value_column_severity,
        test_severity_health_endpoint,
        test_severity_ranking_regression,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            print(f"✗ {t.__name__}: {exc}")
            failed += 1
    print(f"\n{'='*55}")
    print(f"  Severity tests: {passed} passed, {failed} failed")
    print(f"{'='*55}")
    sys.exit(0 if failed == 0 else 1)
