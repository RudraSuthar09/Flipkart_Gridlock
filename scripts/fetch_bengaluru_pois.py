"""
fetch_bengaluru_pois.py — Fetch Points of Interest from OpenStreetMap
                          for Bengaluru and save as a static JSON file.

LOGIC:
------
We query the Overpass API (OSM's free, no-key query engine) to pull three
categories of POIs within Bengaluru's bounding box:

  1. Metro / railway stations  → tag: railway=station or station=subway
  2. Shopping malls / markets  → tag: shop=mall, amenity=marketplace, building=mall
  3. Commercial areas (hospitals, IT parks) → tag: amenity=hospital, landuse=commercial

Why static JSON instead of live queries?
  - Overpass API has rate limits — querying on every page load would be unreliable.
  - POI locations don't change hour-to-hour.
  - Shipping it as a file in /public means zero latency and zero API dependency at demo time.

Output: frontend-react/public/bengaluru_pois.json
  [
    { "name": "Majestic Metro Station", "lat": 12.976, "lon": 77.571, "type": "metro" },
    { "name": "Commercial Street", "lat": 12.983, "lon": 77.607, "type": "market" },
    ...
  ]

Run this ONCE:
  python scripts/fetch_bengaluru_pois.py

No API key needed. Uses OSM's public Overpass API endpoint.
"""

import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

# ─────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────

# Bengaluru bounding box (south, west, north, east)
# This covers the full city including outer ring road areas
BBOX = "12.7343,77.3791,13.1399,77.8395"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "frontend-react" / "public" / "bengaluru_pois.json"

# ─────────────────────────────────────────────────────────
# Overpass queries
# ─────────────────────────────────────────────────────────

# LOGIC: Overpass QL (query language) lets us filter OSM nodes/ways by tags.
# Each tag combo targets a specific category of POI.
# We ask for output in JSON format with center coordinates for area-type features.

QUERIES = {
    "metro": f"""
        [out:json][timeout:30];
        (
          node["railway"="station"]({BBOX});
          node["station"="subway"]({BBOX});
          node["railway"="subway_entrance"]({BBOX});
          way["railway"="station"]({BBOX});
          relation["railway"="station"]({BBOX});
        );
        out center;
    """,

    "market": f"""
        [out:json][timeout:30];
        (
          node["amenity"="marketplace"]({BBOX});
          node["shop"="mall"]({BBOX});
          node["building"="mall"]({BBOX});
          way["amenity"="marketplace"]({BBOX});
          way["shop"="mall"]({BBOX});
          way["building"="mall"]({BBOX});
          node["shop"="supermarket"]({BBOX});
          way["shop"="supermarket"]({BBOX});
        );
        out center;
    """,

    "event": f"""
        [out:json][timeout:30];
        (
          node["amenity"="stadium"]({BBOX});
          node["leisure"="stadium"]({BBOX});
          way["amenity"="stadium"]({BBOX});
          way["leisure"="stadium"]({BBOX});
          node["amenity"="hospital"]["beds"~"[0-9]+"]({BBOX});
          way["landuse"="commercial"]({BBOX});
        );
        out center;
    """,
}

# ─────────────────────────────────────────────────────────
# Fetch helpers
# ─────────────────────────────────────────────────────────

def fetch_overpass(query: str, retries: int = 3) -> dict:
    """
    Send an Overpass QL query and return the parsed JSON response.

    LOGIC: Overpass API accepts POST requests with the query in the body.
    We use Python's built-in urllib (no external deps) to keep this script
    dependency-free. Retry up to 3 times on failure (Overpass can be slow).
    """
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                OVERPASS_URL,
                data=data,
                headers={"User-Agent": "FlipkartGridlock/1.0 (bengaluru-traffic-research)"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(3)
    raise RuntimeError("Overpass API request failed after all retries")


def extract_lat_lon(element: dict):
    """
    LOGIC: OSM has three element types — node (a point), way (a polygon/line),
    relation (a group). For nodes, lat/lon is directly on the element.
    For ways and relations, Overpass returns a 'center' dict when we ask
    for 'out center' — we extract from there.
    """
    if element["type"] == "node":
        return element.get("lat"), element.get("lon")
    else:
        center = element.get("center", {})
        return center.get("lat"), center.get("lon")


def extract_name(element: dict) -> str:
    """Extract the best available name from OSM tags."""
    tags = element.get("tags", {})
    return (
        tags.get("name:en")          # English name first
        or tags.get("name")          # Local name
        or tags.get("official_name")
        or tags.get("alt_name")
        or "Unnamed"
    )


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Fetching Bengaluru POIs from OpenStreetMap (Overpass API)")
    print("No API key needed — this is free public OSM data.")
    print("=" * 60)

    all_pois = []
    seen_ids = set()  # Avoid duplicates (same OSM element matching multiple queries)

    for poi_type, query in QUERIES.items():
        print(f"\n[{poi_type.upper()}] Querying Overpass API...")
        try:
            result = fetch_overpass(query)
            elements = result.get("elements", [])
            print(f"  >> {len(elements)} raw elements returned")

            count = 0
            for elem in elements:
                uid = f"{elem['type']}/{elem['id']}"
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)

                lat, lon = extract_lat_lon(elem)
                if lat is None or lon is None:
                    continue

                # Sanity check: must be within Bengaluru bounds
                if not (12.7 <= lat <= 13.2 and 77.3 <= lon <= 77.9):
                    continue

                name = extract_name(elem)
                all_pois.append({
                    "name": name,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "type": poi_type,
                    "osm_id": uid,
                })
                count += 1

            print(f"  >> {count} valid {poi_type} POIs added")

        except Exception as e:
            print(f"  FAILED to fetch {poi_type}: {e}")
            print("    Continuing with other categories...")

        # Be polite to Overpass API — wait between queries
        time.sleep(2)

    # ── Deduplicate by proximity (50m threshold) ──────────────────
    # LOGIC: Same physical location can appear in multiple OSM elements
    # (e.g., a metro station might be tagged as both a node AND a way).
    # We do a simple proximity dedup: if two POIs of the same type are
    # within 0.0005 degrees (~50m) of each other, keep only the first.
    print(f"\nDeduplicating {len(all_pois)} POIs by proximity...")
    deduped = []
    for poi in all_pois:
        is_dup = False
        for existing in deduped:
            if existing["type"] == poi["type"]:
                dlat = abs(existing["lat"] - poi["lat"])
                dlon = abs(existing["lon"] - poi["lon"])
                if dlat < 0.0005 and dlon < 0.0005:  # ~50m
                    is_dup = True
                    break
        if not is_dup:
            deduped.append(poi)

    # Remove osm_id from final output (not needed by frontend)
    final = [{"name": p["name"], "lat": p["lat"], "lon": p["lon"], "type": p["type"]} for p in deduped]

    # ── Save ──────────────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"OK Saved {len(final)} POIs -> {OUTPUT_PATH}")

    # Summary by type
    for t in ["metro", "market", "event"]:
        n = sum(1 for p in final if p["type"] == t)
        print(f"  {t:10s}: {n}")

    print("=" * 60)
    print("\nNext step: The frontend will load this file automatically from /bengaluru_pois.json")


if __name__ == "__main__":
    main()
