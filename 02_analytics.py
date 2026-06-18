#!/usr/bin/env python3
"""
02_analytics.py
Computes Parking Interference Score (PIS) for every junction:
  vehicle footprint -> per-junction features -> OSMnx betweenness ->
  MinMax-normalised weighted PIS -> action-type mapping -> economic loss.
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
from sklearn.preprocessing import MinMaxScaler
from tqdm import tqdm

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT             = os.path.dirname(os.path.abspath(__file__))
DATA_DIR         = os.path.join(ROOT, "data")
OUT_DIR          = os.path.join(ROOT, "outputs")
os.makedirs(OUT_DIR, exist_ok=True)

VIOLATIONS_CSV   = os.path.join(DATA_DIR, "violations_clean.csv")
CENTRALITY_CACHE = os.path.join(DATA_DIR, "centrality_cache.json")
PIS_CSV          = os.path.join(OUT_DIR,  "pis_scores.csv")

BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH = 77.45, 12.85, 77.75, 13.08
JUNCTION_COL = "junction_name_final"

BLOCKAGE_MAP = {
    "CAR":            4.5,
    "MAXI-CAB":       7.2,
    "LGV":            9.0,
    "SCOOTER":        1.8,
    "MOTOR CYCLE":    1.8,
    "PASSENGER AUTO": 3.2,
    "GOODS AUTO":     3.5,
    "MOPED":          1.5,
    "PRIVATE BUS":    9.5,
    "VAN":            5.0,
}
BLOCKAGE_DEFAULT = 3.0

# Weights must sum to 1.0
PIS_WEIGHTS = {
    "vol_norm":        0.25,
    "repeat_norm":     0.20,
    "blockage_norm":   0.20,
    "enforce_norm":    0.15,
    "centrality_norm": 0.10,
    "peak_norm":       0.10,
}

# ---------------------------------------------------------------------------
# Step 1 -- Load & add blockage_severity
# ---------------------------------------------------------------------------
print("\n[1/6] Loading violations and mapping vehicle footprint ...")
df = pd.read_csv(VIOLATIONS_CSV, low_memory=False)
print(f"  {len(df):,} rows loaded")

df["blockage_severity"] = (
    df["vehicle_type"].map(BLOCKAGE_MAP).fillna(BLOCKAGE_DEFAULT)
)

unmapped = df[~df["vehicle_type"].isin(BLOCKAGE_MAP)]["vehicle_type"].value_counts()
if len(unmapped):
    print(f"  {len(unmapped)} unmapped vehicle types -> default {BLOCKAGE_DEFAULT} m")
    print("  " + ", ".join(f"{t}({n})" for t, n in unmapped.items()))

# ---------------------------------------------------------------------------
# Step 2 -- Per-junction features
# ---------------------------------------------------------------------------
print("\n[2/6] Computing per-junction features ...")

tqdm.pandas(desc="  progress")

groups = df.groupby(JUNCTION_COL, sort=False)

# --- scalar aggregations (fast, single pass) ---
agg = groups.agg(
    violation_volume       = (JUNCTION_COL,       "count"),
    mean_blockage_severity = ("blockage_severity", "mean"),
    lat_mean               = ("latitude",          "mean"),
    lon_mean               = ("longitude",         "mean"),
).reset_index()

# --- repeat_offender_density ---
print("  repeat_offender_density ...")

def _repeat_density(grp):
    vn = grp["vehicle_number"].dropna()
    if vn.empty:
        return 0.0
    counts = vn.value_counts()
    return (counts >= 3).sum() / counts.shape[0]

repeat_s = groups.progress_apply(_repeat_density, include_groups=False)
repeat_df = repeat_s.reset_index()
repeat_df.columns = [JUNCTION_COL, "repeat_offender_density"]

# --- enforcement_failure_rate ---
print("  enforcement_failure_rate ...")

def _enforce_fail(grp):
    total = len(grp)
    if total == 0:
        return 1.0
    approved = (grp["validation_status"] == "approved").sum()
    return round(1.0 - approved / total, 6)

enforce_s = groups.progress_apply(_enforce_fail, include_groups=False)
enforce_df = enforce_s.reset_index()
enforce_df.columns = [JUNCTION_COL, "enforcement_failure_rate"]

# --- peak_hour_share (8am-8pm) ---
print("  peak_hour_share ...")

def _peak_share(grp):
    h = grp["hour"].dropna()
    if h.empty:
        return 0.0
    return float(((h >= 8) & (h < 20)).sum() / len(h))

peak_s = groups.progress_apply(_peak_share, include_groups=False)
peak_df = peak_s.reset_index()
peak_df.columns = [JUNCTION_COL, "peak_hour_share"]

# --- merge all features ---
junc_df = (
    agg
    .merge(repeat_df,  on=JUNCTION_COL)
    .merge(enforce_df, on=JUNCTION_COL)
    .merge(peak_df,    on=JUNCTION_COL)
)
print(f"  {len(junc_df):,} unique junctions after merge")

# ---------------------------------------------------------------------------
# Step 3 -- OSMnx betweenness centrality
# ---------------------------------------------------------------------------
print("\n[3/6] OSMnx betweenness centrality ...")

ox.settings.use_cache = True

if os.path.exists(CENTRALITY_CACHE):
    print("  Loading cached centrality ...")
    with open(CENTRALITY_CACHE) as fh:
        centrality = {int(k): v for k, v in json.load(fh).items()}
    print(f"  {len(centrality):,} node centralities loaded from cache")
    # Still need the graph for nearest-node snapping
    G = ox.graph_from_bbox(
        bbox=(BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH),
        network_type="drive",
    )
else:
    print("  Downloading Bengaluru road network ...")
    G = ox.graph_from_bbox(
        bbox=(BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH),
        network_type="drive",
    )
    print(f"  Graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    k_approx = min(500, G.number_of_nodes())
    print(f"  Computing approximate betweenness centrality (k={k_approx}) ...")
    print("  This takes ~5-15 min on first run; cached afterward.")
    centrality = nx.betweenness_centrality(G, normalized=True, k=k_approx)
    with open(CENTRALITY_CACHE, "w") as fh:
        json.dump({str(k): v for k, v in centrality.items()}, fh)
    print(f"  Cached to {CENTRALITY_CACHE}")

# Snap junction centroids to nearest graph node
valid_mask = junc_df["lat_mean"].notna() & junc_df["lon_mean"].notna()
valid_idx  = junc_df.index[valid_mask]
print(f"  Snapping {valid_mask.sum():,} junction centroids to nearest nodes ...")

node_ids = ox.nearest_nodes(
    G,
    X=junc_df.loc[valid_idx, "lon_mean"].values,
    Y=junc_df.loc[valid_idx, "lat_mean"].values,
)

junc_df["betweenness"] = 0.0
junc_df.loc[valid_idx, "betweenness"] = [
    centrality.get(int(nid), 0.0) for nid in node_ids
]
print(
    f"  Betweenness range: "
    f"[{junc_df['betweenness'].min():.6f}, {junc_df['betweenness'].max():.6f}]"
)

# ---------------------------------------------------------------------------
# Step 4 -- PIS: MinMax normalise then weighted sum
# ---------------------------------------------------------------------------
print("\n[4/6] Computing PIS scores ...")

raw_features = [
    "violation_volume",
    "repeat_offender_density",
    "mean_blockage_severity",
    "enforcement_failure_rate",
    "betweenness",
    "peak_hour_share",
]
norm_cols = [
    "vol_norm",
    "repeat_norm",
    "blockage_norm",
    "enforce_norm",
    "centrality_norm",
    "peak_norm",
]

scaler = MinMaxScaler()
scaled = scaler.fit_transform(junc_df[raw_features].fillna(0.0))
norm_df = pd.DataFrame(scaled, columns=norm_cols, index=junc_df.index)
junc_df = pd.concat([junc_df, norm_df], axis=1)

junc_df["PIS"] = (
    sum(junc_df[col] * w for col, w in PIS_WEIGHTS.items())
).round(4)

junc_df["rank"] = (
    junc_df["PIS"].rank(ascending=False, method="min").astype(int)
)
print(
    f"  PIS range: [{junc_df['PIS'].min():.4f}, {junc_df['PIS'].max():.4f}]  "
    f"| median: {junc_df['PIS'].median():.4f}"
)

# ---------------------------------------------------------------------------
# Step 5 -- Action type mapping
# ---------------------------------------------------------------------------
print("\n[5/6] Assigning action types ...")

def _action(row):
    p = row["PIS"]
    r = row["repeat_offender_density"]
    e = row["enforcement_failure_rate"]
    if p >= 0.75 and r >= 0.30:
        return "Tow + Fleet Alert"
    if p >= 0.75:
        return "Add Loading Bay"
    if p >= 0.50 and e >= 0.40:
        return "Deploy Patrol"
    if p >= 0.50:
        return "Audit Camera"
    return "Monitor"

junc_df["action_type"] = junc_df.apply(_action, axis=1)
print(junc_df["action_type"].value_counts().to_string())

# ---------------------------------------------------------------------------
# Step 6 -- Economic loss
# ---------------------------------------------------------------------------
print("\n[6/6] Computing economic loss ...")

junc_df["vehicle_hours_lost_per_day"] = (
    junc_df["mean_blockage_severity"] * junc_df["violation_volume"] * 0.5 / 3600 * 100
).round(4)

junc_df["loss_INR_per_day"] = (
    junc_df["vehicle_hours_lost_per_day"] * 150
).round(2)

total_loss = junc_df["loss_INR_per_day"].sum()
print(f"  Total estimated daily loss across all junctions: INR {total_loss:,.0f}")

# ---------------------------------------------------------------------------
# Save & report
# ---------------------------------------------------------------------------
OUTPUT_COLS = [
    JUNCTION_COL,
    "lat_mean", "lon_mean",
    "violation_volume",
    "repeat_offender_density",
    "mean_blockage_severity",
    "enforcement_failure_rate",
    "peak_hour_share",
    "betweenness",
    # normalised
    "vol_norm", "repeat_norm", "blockage_norm",
    "enforce_norm", "centrality_norm", "peak_norm",
    # scores
    "PIS", "rank", "action_type",
    # economics
    "vehicle_hours_lost_per_day", "loss_INR_per_day",
]

junc_df[OUTPUT_COLS].sort_values("rank").to_csv(PIS_CSV, index=False)
print(f"\nSaved {len(junc_df):,} junctions -> {PIS_CSV}")

top10 = junc_df.nsmallest(10, "rank")[
    [
        JUNCTION_COL, "PIS", "rank", "action_type",
        "violation_volume", "repeat_offender_density",
        "enforcement_failure_rate", "loss_INR_per_day",
    ]
]
print("\n=== Top 10 Junctions by PIS ===")
pd.set_option("display.max_colwidth", 40)
pd.set_option("display.width", 160)
print(top10.to_string(index=False))
print("\nDone.")
