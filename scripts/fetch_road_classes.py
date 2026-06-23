"""
fetch_road_classes.py — Snap all 6,333 Bengaluru violation locations to the
                         nearest OSM road and extract highway class data.

VERSION 2: Uses Overpass API directly (no osmnx graph download needed).
           This is far more reliable on flaky internet because we make
           small tiled queries instead of one massive graph download.

LOGIC (step by step):
---------------------
STEP 1 — Divide Bengaluru into tiles
  We split the city bounding box into a grid of ~0.05 degree tiles
  (~5.5km each). Each tile is a separate Overpass query — if one fails,
  we retry it independently. Much more reliable than one huge download.

STEP 2 — Query roads per tile via Overpass API
  For each tile, we ask Overpass: "give me all ways tagged highway=*
  inside this bounding box, with their node coordinates."
  We parse each way into a list of (lat, lon) segments with its
  highway tag and oneway/name attributes.

STEP 3 — For each hotspot location, find the nearest road segment
  Simple nearest-segment search using point-to-line-segment distance.
  We use a spatial grid to avoid checking every segment for every location.

STEP 4 — Map highway class to tier + road_weight
  Same mapping as before (primary=0.20, residential=0.70, etc.)

STEP 5 — Save as JSON lookup
  Output: data/road_class_lookup.json

Run:  python scripts/fetch_road_classes.py
No API key needed. No osmnx dependency required.
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Tuple, Dict, Optional

import numpy as np
import pandas as pd

# ── Allow running from project root ──────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prediction_api"))

from app.config import RAW_CSV, DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

OUTPUT_PATH = DATA_DIR / "road_class_lookup.json"

# ─────────────────────────────────────────────────────────────────
# Bengaluru bounding box
# ─────────────────────────────────────────────────────────────────
BBOX_SOUTH = 12.7343
BBOX_WEST  = 77.3791
BBOX_NORTH = 13.1399
BBOX_EAST  = 77.8395

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",  # fallback mirror
]
TILE_SIZE    = 0.05   # degrees (~5.5km per tile)

# ─────────────────────────────────────────────────────────────────
# Highway class -> tier + road_weight mapping
# ─────────────────────────────────────────────────────────────────
# Road types that vehicles can actually use — used to prefer these in snap
DRIVEABLE_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "residential", "living_street",
    "unclassified", "service",
}

HIGHWAY_MAP = {
    "motorway":       {"tier": 0, "road_weight": 0.15, "label": "Motorway"},
    "trunk":          {"tier": 0, "road_weight": 0.15, "label": "Trunk Road"},
    "motorway_link":  {"tier": 0, "road_weight": 0.15, "label": "Motorway Link"},
    "trunk_link":     {"tier": 0, "road_weight": 0.15, "label": "Trunk Link"},
    "primary":        {"tier": 1, "road_weight": 0.20, "label": "Primary Road"},
    "primary_link":   {"tier": 1, "road_weight": 0.20, "label": "Primary Link"},
    "secondary":      {"tier": 2, "road_weight": 0.30, "label": "Secondary Road"},
    "secondary_link": {"tier": 2, "road_weight": 0.30, "label": "Secondary Link"},
    "tertiary":       {"tier": 3, "road_weight": 0.45, "label": "Tertiary Road"},
    "tertiary_link":  {"tier": 3, "road_weight": 0.45, "label": "Tertiary Link"},
    "residential":    {"tier": 4, "road_weight": 0.70, "label": "Residential Road"},
    "living_street":  {"tier": 4, "road_weight": 0.80, "label": "Living Street"},
    "unclassified":   {"tier": 4, "road_weight": 0.70, "label": "Unclassified Road"},
    "service":        {"tier": 5, "road_weight": 0.90, "label": "Service Lane"},
    "track":          {"tier": 5, "road_weight": 0.90, "label": "Track"},
    "path":           {"tier": 5, "road_weight": 0.95, "label": "Path"},
    "footway":        {"tier": 5, "road_weight": 1.00, "label": "Footway"},
    "cycleway":       {"tier": 5, "road_weight": 1.00, "label": "Cycleway"},
    "pedestrian":     {"tier": 5, "road_weight": 1.00, "label": "Pedestrian Zone"},
}
DEFAULT_HIGHWAY = {"tier": 3, "road_weight": 0.45, "label": "Unknown Road"}


# ─────────────────────────────────────────────────────────────────
# Overpass query helpers
# ─────────────────────────────────────────────────────────────────

def fetch_overpass(query: str, retries: int = 4) -> dict:
    """
    Send an Overpass query and return JSON. Rotates between mirror URLs and
    uses exponential backoff so 429 rate-limit errors recover gracefully.
    """
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    backoff = [5, 15, 45, 90]  # seconds per attempt — 429 needs real wait time
    for attempt in range(retries):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"User-Agent": "FlipkartGridlock/1.0"}
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            wait = backoff[min(attempt, len(backoff) - 1)]
            log.warning("  Overpass attempt %d/%d failed (%s): %s — waiting %ds",
                        attempt + 1, retries, url.split("/")[2], e, wait)
            if attempt < retries - 1:
                time.sleep(wait)
    return None  # all retries failed


def fetch_roads_in_tile(south: float, west: float, north: float, east: float) -> Optional[List[dict]]:
    """
    Query Overpass for all highway ways in a bounding box tile.
    Returns list of road segments, or None if the fetch failed (all retries exhausted).

    LOGIC: We request ways with `highway` tag (any road type) and ask
    for geometry output (out:json with `geom` gives us node coordinates
    directly — no need for a separate node lookup).
    """
    query = f"""
        [out:json][timeout:60];
        way["highway"]({south},{west},{north},{east});
        out body geom;
    """
    result = fetch_overpass(query)
    if result is None:
        return None  # signal failure — distinct from [] (tile has no roads)

    roads = []
    for elem in result.get("elements", []):
        if elem.get("type") != "way":
            continue
        tags = elem.get("tags", {})
        hw = tags.get("highway", "unclassified")
        if isinstance(hw, list):
            hw = hw[0]
        name = tags.get("name", None)
        oneway = tags.get("oneway", "no") in ("yes", "true", "1", "-1")

        geom = elem.get("geometry", [])
        if len(geom) < 2:
            continue

        nodes = [(pt["lat"], pt["lon"]) for pt in geom]
        roads.append({
            "highway": hw.lower().strip(),
            "name": name,
            "oneway": oneway,
            "nodes": nodes,
        })
    return roads


# ─────────────────────────────────────────────────────────────────
# Geometry: point-to-segment distance
# ─────────────────────────────────────────────────────────────────

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Haversine distance in metres between two lat/lon points."""
    R = 6371000
    to_rad = math.pi / 180
    dlat = (lat2 - lat1) * to_rad
    dlon = (lon2 - lon1) * to_rad
    a = math.sin(dlat/2)**2 + math.cos(lat1*to_rad) * math.cos(lat2*to_rad) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def point_to_segment_dist(plat, plon, alat, alon, blat, blon) -> Tuple[float, float, float]:
    """
    Approximate distance from point P to line segment A-B.
    Returns (distance_m, closest_lat, closest_lon).

    LOGIC: We project P onto the line A-B using a simple linear projection
    in lat/lon space (valid for small distances). Then clamp the projection
    parameter t to [0,1] so we stay on the segment. Finally compute
    Haversine distance to the closest point.
    """
    # Vector from A to B
    dx = blon - alon
    dy = blat - alat
    len_sq = dx*dx + dy*dy

    if len_sq < 1e-14:
        # A and B are the same point
        return haversine_m(plat, plon, alat, alon), alat, alon

    # Project P onto line A-B: t = dot(AP, AB) / |AB|^2
    t = ((plon - alon) * dx + (plat - alat) * dy) / len_sq
    t = max(0.0, min(1.0, t))  # clamp to segment

    clat = alat + t * dy
    clon = alon + t * dx
    dist = haversine_m(plat, plon, clat, clon)
    return dist, clat, clon


# ─────────────────────────────────────────────────────────────────
# Spatial grid for fast nearest-road lookup
# ─────────────────────────────────────────────────────────────────

class RoadSegmentIndex:
    """
    Grid-based spatial index of road segments for fast nearest-segment queries.

    LOGIC: We split each road way into individual segments (pairs of consecutive
    nodes). Each segment is stored in the grid cell containing its midpoint.
    To find the nearest road to a query point, we search the surrounding
    3x3 grid cells and compute exact point-to-segment distances only for
    segments in those cells. This reduces comparisons from O(total_segments)
    to O(nearby_segments) per query.
    """
    def __init__(self, cell_size=0.005):
        self.cell_size = cell_size
        self.grid: Dict[str, List[dict]] = {}
        self.total_segments = 0

    def _key(self, lat, lon):
        return f"{int(lat / self.cell_size)},{int(lon / self.cell_size)}"

    def add_road(self, road: dict):
        """Add all segments of a road to the grid."""
        nodes = road["nodes"]
        for i in range(len(nodes) - 1):
            a_lat, a_lon = nodes[i]
            b_lat, b_lon = nodes[i + 1]
            mid_lat = (a_lat + b_lat) / 2
            mid_lon = (a_lon + b_lon) / 2
            key = self._key(mid_lat, mid_lon)
            seg = {
                "a": (a_lat, a_lon),
                "b": (b_lat, b_lon),
                "highway": road["highway"],
                "name": road["name"],
                "oneway": road["oneway"],
            }
            if key not in self.grid:
                self.grid[key] = []
            self.grid[key].append(seg)
            self.total_segments += 1

    def nearest(self, lat, lon, search_radius=2) -> Optional[dict]:
        """
        Find the nearest road segment to a given point.
        Prefers driveable road types (motorway → service) over footways/paths.
        Falls back to any road type if no driveable road is found nearby.
        """
        base_r = int(lat / self.cell_size)
        base_c = int(lon / self.cell_size)

        best_dist = float("inf")
        best_seg = None
        best_drive_dist = float("inf")
        best_drive_seg = None

        for dr in range(-search_radius, search_radius + 1):
            for dc in range(-search_radius, search_radius + 1):
                key = f"{base_r + dr},{base_c + dc}"
                segs = self.grid.get(key)
                if not segs:
                    continue
                for seg in segs:
                    dist, _, _ = point_to_segment_dist(
                        lat, lon, seg["a"][0], seg["a"][1], seg["b"][0], seg["b"][1]
                    )
                    if dist < best_dist:
                        best_dist = dist
                        best_seg = seg
                    if seg["highway"] in DRIVEABLE_HIGHWAYS and dist < best_drive_dist:
                        best_drive_dist = dist
                        best_drive_seg = seg

        # Prefer driveable road if it's within 50m; otherwise use whatever is closest
        chosen = best_drive_seg if (best_drive_seg and best_drive_dist <= 50) else best_seg
        if chosen is None:
            return None
        snap_dist = best_drive_dist if chosen is best_drive_seg else best_dist
        return {**chosen, "snap_dist_m": round(snap_dist, 1)}


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main() -> int:
    log.info("=" * 65)
    log.info("FETCH ROAD CLASSES (v2 - Overpass API, no osmnx needed)")
    log.info("=" * 65)

    # ── STEP 1: Generate tile grid ───────────────────────────────
    tiles = []
    lat = BBOX_SOUTH
    while lat < BBOX_NORTH:
        lon = BBOX_WEST
        while lon < BBOX_EAST:
            tiles.append((
                round(lat, 4),
                round(lon, 4),
                round(min(lat + TILE_SIZE, BBOX_NORTH), 4),
                round(min(lon + TILE_SIZE, BBOX_EAST), 4),
            ))
            lon += TILE_SIZE
        lat += TILE_SIZE

    log.info("STEP 1: %d tiles covering Bengaluru (%.3f deg each)", len(tiles), TILE_SIZE)

    # ── STEP 2: Fetch roads from Overpass, tile by tile ──────────
    log.info("STEP 2: Fetching roads from Overpass API tile by tile...")
    log.info("  Each tile is a separate HTTP request -- resilient to drops.")

    # Resume support: if a partial cache file exists, load already-snapped locations
    # so we don't re-fetch everything on a restart.
    TILE_CACHE = DATA_DIR / "road_class_tile_cache.json"
    cached_roads_data: List[dict] = []
    if TILE_CACHE.exists():
        try:
            with open(TILE_CACHE, encoding="utf-8") as f:
                cached_roads_data = json.load(f)
            log.info("  Resuming: loaded %d roads from tile cache", len(cached_roads_data))
        except Exception:
            cached_roads_data = []

    road_index = RoadSegmentIndex(cell_size=0.005)
    for road in cached_roads_data:
        road_index.add_road(road)

    all_roads: List[dict] = list(cached_roads_data)
    failed_tile_indices: List[int] = []
    total_roads = len(cached_roads_data)

    for i, (s, w, n, e) in enumerate(tiles):
        roads = fetch_roads_in_tile(s, w, n, e)
        if roads is None:
            failed_tile_indices.append(i)
            log.warning("  Tile %d/%d FAILED (will retry later)", i + 1, len(tiles))
        else:
            total_roads += len(roads)
            all_roads.extend(roads)
            for road in roads:
                road_index.add_road(road)

        # Progress every 20 tiles
        if (i + 1) % 20 == 0 or i == len(tiles) - 1:
            log.info("  Tiles: %d/%d done | Roads so far: %d | Segments: %d",
                     i + 1, len(tiles), total_roads, road_index.total_segments)
            # Save partial cache so we can resume if interrupted
            try:
                with open(TILE_CACHE, "w", encoding="utf-8") as f:
                    json.dump(all_roads, f)
            except Exception as e:
                log.warning("  Could not write tile cache: %s", e)

        # Polite delay — Overpass rate-limits aggressively; 2s is the minimum safe interval
        time.sleep(2.0)

    # Retry only the tiles that actually failed (not all tiles)
    if failed_tile_indices:
        log.warning("  %d tiles failed. Retrying failed tiles only...", len(failed_tile_indices))
        still_failed = 0
        for idx in failed_tile_indices:
            s, w, n, e = tiles[idx]
            roads = fetch_roads_in_tile(s, w, n, e)
            if roads is not None:
                total_roads += len(roads)
                all_roads.extend(roads)
                for road in roads:
                    road_index.add_road(road)
            else:
                still_failed += 1
                log.warning("  Tile %d still failed after retry", idx + 1)
            time.sleep(1)
        if still_failed:
            log.warning("  %d tiles could not be fetched. Coverage may be incomplete.", still_failed)

    # Clean up tile cache on success
    if TILE_CACHE.exists():
        TILE_CACHE.unlink()
        log.info("  Tile cache cleaned up.")

    log.info("  Total roads fetched: %d | Total segments indexed: %d",
             total_roads, road_index.total_segments)

    if road_index.total_segments == 0:
        log.error("No road segments fetched. Check internet connection.")
        return 1

    # ── STEP 3: Load our 6,333 hotspot locations ─────────────────
    log.info("STEP 3: Loading hotspot locations from %s", RAW_CSV)
    raw = pd.read_csv(RAW_CSV, low_memory=False)

    bad = (
        raw["location_key"].isna()
        | (raw["location_key"].astype(str).str.strip() == "")
        | (raw["location_key"].astype(str).str.strip() == "No Junction")
    )
    raw = raw[~bad].copy()

    def first_valid(s):
        v = s.dropna()
        return v.iloc[0] if len(v) else None

    loc_df = (
        raw.groupby("location_key", sort=False)
        .agg(lat=("latitude", first_valid), lon=("longitude", first_valid))
        .reset_index()
        .dropna(subset=["lat", "lon"])
    )
    log.info("  %d unique locations to snap", len(loc_df))

    # ── STEP 4: Snap each location to nearest road segment ───────
    log.info("STEP 4: Snapping locations to nearest road segments...")
    t0 = time.time()

    results = {}
    no_match = 0

    for _, row in loc_df.iterrows():
        loc_key = row["location_key"]
        lat, lon = float(row["lat"]), float(row["lon"])

        match = road_index.nearest(lat, lon)
        if match is None:
            no_match += 1
            results[loc_key] = {
                "highway":      "unclassified",
                "tier":         DEFAULT_HIGHWAY["tier"],
                "road_weight":  DEFAULT_HIGHWAY["road_weight"],
                "road_label":   DEFAULT_HIGHWAY["label"],
                "is_oneway":    False,
                "snap_dist_m":  -1,
                "osm_name":     None,
            }
            continue

        hw = match["highway"]
        info = HIGHWAY_MAP.get(hw, DEFAULT_HIGHWAY)

        results[loc_key] = {
            "highway":      hw,
            "tier":         info["tier"],
            "road_weight":  info["road_weight"],
            "road_label":   info["label"],
            "is_oneway":    match["oneway"],
            "snap_dist_m":  match["snap_dist_m"],
            "osm_name":     match["name"],
        }

    elapsed = time.time() - t0
    log.info("  Snapped %d locations in %.1fs (%d unmatched)",
             len(results), elapsed, no_match)

    # ── Stats ─────────────────────────────────────────────────────
    log.info("STEP 5: Highway class distribution:")
    hw_counts: Dict[str, int] = {}
    for r in results.values():
        hw_counts[r["highway"]] = hw_counts.get(r["highway"], 0) + 1
    for hw, cnt in sorted(hw_counts.items(), key=lambda x: -x[1])[:12]:
        info = HIGHWAY_MAP.get(hw, DEFAULT_HIGHWAY)
        log.info("    %-25s  %4d locs  road_weight=%.2f  tier=%d",
                 hw, cnt, info["road_weight"], info["tier"])

    one_way_count = sum(1 for r in results.values() if r["is_oneway"])
    log.info("  One-way roads: %d / %d (%.1f%%)",
             one_way_count, len(results), 100 * one_way_count / max(len(results), 1))

    # ── Compare with existing lane_count ──────────────────────────
    lc_map = raw.groupby("location_key")["lane_count"].mean().to_dict()
    improvements = 0
    for loc_key, r in results.items():
        existing_lc = lc_map.get(loc_key, None)
        if existing_lc is not None:
            existing_rw = round(1.0 / max(existing_lc, 0.5), 2)
            if abs(r["road_weight"] - existing_rw) > 0.15:
                improvements += 1

    log.info("  OSM gives different road_weight for %d / %d locations (%.1f%%)",
             improvements, len(results), 100 * improvements / max(len(results), 1))

    # ── Save ──────────────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log.info("=" * 65)
    log.info("DONE -- %d locations saved -> %s", len(results), OUTPUT_PATH)
    log.info("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
