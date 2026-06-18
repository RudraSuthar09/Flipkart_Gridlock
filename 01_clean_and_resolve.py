#!/usr/bin/env python3
"""
01_clean_and_resolve.py
Pipeline: clean parking-violation data, resolve No Junction names via H3+OSMnx,
audit devices for blind-spot risk, compute per-station SCITA funnel metrics.
"""

import os
import warnings
import numpy as np
import pandas as pd
import h3
import osmnx as ox
from pyproj import Transformer
from tqdm import tqdm

warnings.filterwarnings("ignore")

# -- Config ----------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_IN = os.path.join(ROOT, "dataset.csv")
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Bengaluru bbox as (west, south, east, north) for osmnx v2
BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH = 77.45, 12.85, 77.75, 13.08
H3_RES = 8
MAX_DIST_M = 150.0

# -- Step 1: Load & parse datetime -----------------------------------------------
print("\n[1/5] Loading dataset ...")
df = pd.read_csv(DATA_IN, low_memory=False)
print(f"  Loaded {len(df):,} rows x {len(df.columns)} columns")

df["created_datetime"] = pd.to_datetime(df["created_datetime"], utc=True, errors="coerce")

df["hour"]        = df["created_datetime"].dt.hour
df["day_of_week"] = df["created_datetime"].dt.day_name()
df["month"]       = df["created_datetime"].dt.month_name()

null_dt = df["created_datetime"].isna().sum()
if null_dt:
    print(f"  Warning: {null_dt:,} rows with unparseable created_datetime")

# -- Step 2: Resolve "No Junction" via H3 geohash + OSMnx nearest road -----------
print("\n[2/5] Resolving 'No Junction' records ...")

no_junc_mask = df["junction_name"] == "No Junction"
nj_idx = df.index[no_junc_mask]
nj_lat = df.loc[nj_idx, "latitude"]
nj_lon = df.loc[nj_idx, "longitude"]
valid_mask = nj_lat.notna() & nj_lon.notna()
valid_idx = nj_idx[valid_mask.values]

print(f"  {no_junc_mask.sum():,} 'No Junction' records  ({valid_mask.sum():,} with valid coords)")

# Assign H3 cells (vectorised loop with tqdm)
h3_cells = np.full(len(valid_idx), None, dtype=object)
for i, (lat, lon) in enumerate(
    tqdm(zip(nj_lat[valid_mask].values, nj_lon[valid_mask].values),
         total=valid_mask.sum(), desc="  H3 cell assignment", unit="rec")
):
    h3_cells[i] = h3.latlng_to_cell(float(lat), float(lon), H3_RES)

df.loc[valid_idx, "h3_cell"] = h3_cells

# Unique H3 cells -> centroid coords for OSMnx queries
unique_cells = df["h3_cell"].dropna().unique()
print(f"  {len(unique_cells):,} unique H3-{H3_RES} cells to query")

cell_lat = np.array([h3.cell_to_latlng(c)[0] for c in unique_cells])
cell_lon = np.array([h3.cell_to_latlng(c)[1] for c in unique_cells])

# Download Bengaluru drive network (osmnx caches to disk automatically)
print("  Fetching Bengaluru road network via OSMnx (cached after first run) ...")
ox.settings.use_cache = True
G = ox.graph_from_bbox(
    bbox=(BBOX_WEST, BBOX_SOUTH, BBOX_EAST, BBOX_NORTH),
    network_type="drive",
    retain_all=False,
)
G_proj = ox.project_graph(G)
graph_crs = G_proj.graph["crs"]
print(f"  Graph: {G_proj.number_of_nodes():,} nodes , {G_proj.number_of_edges():,} edges , CRS: {graph_crs}")

# Project H3 centroids into graph CRS for metric distance calc
transformer = Transformer.from_crs("EPSG:4326", graph_crs, always_xy=True)
x_proj, y_proj = transformer.transform(cell_lon, cell_lat)

# Vectorised nearest-edge search (one call, returns dist in metres for projected graph)
print("  Running nearest-edge search for all H3 centroids ...")
edge_tuples, dists = ox.nearest_edges(G_proj, X=x_proj, Y=y_proj, return_dist=True)

# Build edge attribute lookup once
edge_attr = {(u, v, k): d for u, v, k, d in G_proj.edges(keys=True, data=True)}

def _road_name(edata: dict) -> str:
    name = edata.get("name")
    if isinstance(name, list):
        name = name[0]
    if name and str(name).strip():
        return str(name).strip()
    ref = edata.get("ref")
    if isinstance(ref, list):
        ref = ref[0]
    if ref and str(ref).strip():
        return str(ref).strip()
    return "Unnamed Road"

cell_to_road: dict[str, str] = {}
for cell, edge, dist in tqdm(
    zip(unique_cells, edge_tuples, dists),
    total=len(unique_cells),
    desc="  Mapping road names",
    unit="cell",
):
    if dist <= MAX_DIST_M:
        cell_to_road[cell] = _road_name(edge_attr.get(tuple(edge), {}))

resolved = df["h3_cell"].map(cell_to_road)
resolved_count = resolved.notna().sum()
print(
    f"  Resolved {resolved_count:,} / {no_junc_mask.sum():,} records "
    f"({100 * resolved_count / max(no_junc_mask.sum(), 1):.1f}%)"
)

# Apply: fill junction_name_final; unresolved "No Junction" records keep their label
df["junction_name_final"] = df["junction_name"].copy()
update_mask = no_junc_mask & resolved.notna()
df.loc[update_mask, "junction_name_final"] = resolved[update_mask]

# -- Step 3: Device blind-spot audit --------------------------------------------
print("\n[3/5] Computing rejection rates per device_id ...")

device_audit = (
    df.groupby("device_id", sort=False)
    .agg(
        total_records   = ("id", "count"),
        rejected_count  = ("validation_status", lambda x: (x == "rejected").sum()),
        approved_count  = ("validation_status", lambda x: (x == "approved").sum()),
    )
    .reset_index()
)
device_audit["rejection_rate"] = (
    device_audit["rejected_count"] / device_audit["total_records"]
).round(4)
device_audit["blind_spot_risk"] = device_audit["rejection_rate"] > 0.25

n_risky = device_audit["blind_spot_risk"].sum()
print(
    f"  {n_risky:,} / {len(device_audit):,} devices flagged as blind_spot_risk "
    f"(rejection_rate > 25%)"
)

# -- Step 4: Police-station SCITA funnel ----------------------------------------
print("\n[4/5] Computing SCITA send rates per police_station ...")

station_funnel = (
    df.groupby("police_station", sort=False)
    .agg(
        total_records  = ("id", "count"),
        sent_to_scita  = ("data_sent_to_scita", lambda x: x.astype(bool).sum()),
    )
    .reset_index()
)
station_funnel["scita_send_rate"] = (
    station_funnel["sent_to_scita"] / station_funnel["total_records"]
).round(4)
station_funnel["low_scita_flag"] = station_funnel["scita_send_rate"] < 0.75

n_low = station_funnel["low_scita_flag"].sum()
print(
    f"  {n_low:,} / {len(station_funnel):,} stations flagged "
    f"(SCITA send rate < 75%)"
)

# -- Step 5: Save outputs -------------------------------------------------------
print("\n[5/5] Saving outputs ...")

CLEAN_COLS = [
    "id", "latitude", "longitude",
    "vehicle_number", "vehicle_type", "violation_type",
    "created_datetime", "hour", "day_of_week", "month",
    "device_id", "police_station", "junction_name_final",
    "validation_status", "data_sent_to_scita", "action_taken_timestamp",
]

violations_path = os.path.join(DATA_DIR, "violations_clean.csv")
device_path     = os.path.join(DATA_DIR, "device_audit.csv")
station_path    = os.path.join(DATA_DIR, "station_funnel.csv")

df[CLEAN_COLS].to_csv(violations_path, index=False)
print(f"  violations_clean.csv  -> {len(df):,} rows")

device_audit.to_csv(device_path, index=False)
print(f"  device_audit.csv      -> {len(device_audit):,} rows")

station_funnel.to_csv(station_path, index=False)
print(f"  station_funnel.csv    -> {len(station_funnel):,} rows")

print("\nAll done.")
