#!/usr/bin/env python3
"""
03_dark_fleet.py
Detects organised parking-violation fleets via bipartite NetworkX graph
and Louvain community detection.
"""

import os
import warnings
import numpy as np
import pandas as pd
import networkx as nx
from networkx.algorithms import bipartite
import community as community_louvain
from tqdm import tqdm

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
OUT_DIR  = os.path.join(ROOT, "outputs")
os.makedirs(OUT_DIR, exist_ok=True)

VIOLATIONS_CSV     = os.path.join(DATA_DIR, "violations_clean.csv")
DARK_FLEET_CSV     = os.path.join(OUT_DIR, "dark_fleet.csv")
FLEET_EDGES_CSV    = os.path.join(OUT_DIR, "fleet_graph_edges.csv")

MIN_JUNCTIONS  = 3
MIN_VIOLATIONS = 10

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
print("\n[1/6] Loading violations ...")
df = pd.read_csv(VIOLATIONS_CSV, low_memory=False)
df = df.dropna(subset=["vehicle_number", "junction_name_final"])
print(f"  {len(df):,} rows after dropping null vehicle/junction")

# ---------------------------------------------------------------------------
# Step 1 — Build bipartite graph (all vehicles x all junctions)
# ---------------------------------------------------------------------------
print("\n[2/6] Building bipartite vehicle <-> junction graph ...")

pair_counts = (
    df.groupby(["vehicle_number", "junction_name_final"])
    .size()
    .reset_index(name="weight")
)

B = nx.Graph()
for _, row in tqdm(pair_counts.iterrows(), total=len(pair_counts),
                   desc="  Adding edges", unit="pair"):
    vn = row["vehicle_number"]
    jn = row["junction_name_final"]
    B.add_node(vn, bipartite=0)
    B.add_node(jn, bipartite=1)
    B.add_edge(vn, jn, weight=int(row["weight"]))

vehicle_nodes_all = {n for n, d in B.nodes(data=True) if d["bipartite"] == 0}
junction_nodes_all = {n for n, d in B.nodes(data=True) if d["bipartite"] == 1}
print(
    f"  Graph: {len(vehicle_nodes_all):,} vehicles, "
    f"{len(junction_nodes_all):,} junctions, "
    f"{B.number_of_edges():,} edges"
)

# ---------------------------------------------------------------------------
# Step 2 — Filter: 3+ distinct junctions AND 10+ total violations
# ---------------------------------------------------------------------------
print("\n[3/6] Filtering fleet vehicles ...")

vehicle_stats = (
    df.groupby("vehicle_number")
    .agg(
        total_hits         = ("id",                  "count"),
        distinct_junctions = ("junction_name_final", "nunique"),
    )
    .reset_index()
)

fleet_mask = (
    (vehicle_stats["distinct_junctions"] >= MIN_JUNCTIONS) &
    (vehicle_stats["total_hits"]         >= MIN_VIOLATIONS)
)
fleet_vehicles = set(vehicle_stats.loc[fleet_mask, "vehicle_number"])
print(
    f"  {len(fleet_vehicles):,} vehicles pass "
    f"(>={MIN_JUNCTIONS} junctions, >={MIN_VIOLATIONS} violations)"
)

# Sub-graph of fleet vehicles only (keep all their junction neighbours)
fleet_pair_counts = pair_counts[pair_counts["vehicle_number"].isin(fleet_vehicles)]

B_fleet = nx.Graph()
for _, row in fleet_pair_counts.iterrows():
    vn = row["vehicle_number"]
    jn = row["junction_name_final"]
    B_fleet.add_node(vn, bipartite=0)
    B_fleet.add_node(jn, bipartite=1)
    B_fleet.add_edge(vn, jn, weight=int(row["weight"]))

# ---------------------------------------------------------------------------
# Step 3 — Community detection on vehicle-only projected graph
# ---------------------------------------------------------------------------
print("\n[4/6] Projecting graph onto vehicles and running Louvain ...")

fleet_v_nodes = {n for n, d in B_fleet.nodes(data=True) if d["bipartite"] == 0}
G_proj = bipartite.weighted_projected_graph(B_fleet, fleet_v_nodes)
print(
    f"  Projected graph: {G_proj.number_of_nodes()} vehicles, "
    f"{G_proj.number_of_edges()} shared-junction edges"
)

np.random.seed(42)
partition = community_louvain.best_partition(G_proj, random_state=42)
n_clusters = len(set(partition.values()))
print(f"  Louvain found {n_clusters} fleet clusters")

# ---------------------------------------------------------------------------
# Step 4 — Fleet leaders (highest total_hits per cluster)
# ---------------------------------------------------------------------------
print("\n[5/6] Identifying fleet leaders ...")

junction_lists = (
    df[df["vehicle_number"].isin(fleet_vehicles)]
    .groupby("vehicle_number")["junction_name_final"]
    .apply(lambda x: ";".join(sorted(set(x.dropna()))))
    .reset_index()
    .rename(columns={"junction_name_final": "junction_list"})
)

fleet_df = (
    vehicle_stats[vehicle_stats["vehicle_number"].isin(fleet_vehicles)]
    .copy()
    .merge(junction_lists, on="vehicle_number", how="left")
)

fleet_df["fleet_cluster_id"] = fleet_df["vehicle_number"].map(partition)

# Mark tied leaders (all vehicles with max hits in cluster)
fleet_df["is_fleet_leader"] = fleet_df.groupby("fleet_cluster_id")["total_hits"].transform(
    lambda x: x == x.max()
)

n_leaders = fleet_df["is_fleet_leader"].sum()
print(f"  {n_leaders} fleet leaders identified across {n_clusters} clusters")

# ---------------------------------------------------------------------------
# Step 5 — Save outputs
# ---------------------------------------------------------------------------
print("\n[6/6] Saving ...")

fleet_df[
    ["vehicle_number", "total_hits", "distinct_junctions",
     "junction_list", "fleet_cluster_id", "is_fleet_leader"]
].sort_values(["fleet_cluster_id", "total_hits"], ascending=[True, False]
).to_csv(DARK_FLEET_CSV, index=False)
print(f"  dark_fleet.csv        -> {len(fleet_df):,} rows")

edges_out = (
    fleet_pair_counts
    .rename(columns={"junction_name_final": "junction_name"})
    [["vehicle_number", "junction_name", "weight"]]
)
edges_out.to_csv(FLEET_EDGES_CSV, index=False)
print(f"  fleet_graph_edges.csv -> {len(edges_out):,} rows")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
top5 = fleet_df.nlargest(5, "total_hits")[
    ["vehicle_number", "total_hits", "distinct_junctions",
     "fleet_cluster_id", "is_fleet_leader"]
]
print(f"\n  Clusters   : {n_clusters}")
print(f"  Fleet size : {len(fleet_df)} vehicles")
print("\n  Top 5 offenders:")
print(top5.to_string(index=False))
print("\nDone.")
