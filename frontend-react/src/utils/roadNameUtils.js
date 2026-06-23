const OVERPASS = 'https://overpass-api.de/api/interpreter';

// In-memory cache: location_key → [{name, highway}]
const cache = new Map();

/**
 * Fetch road names (OSM way names) within 100 m of a point.
 * Uses tags-only query — ~200 bytes response, no geometry.
 */
export async function fetchRoadNames(lat, lon, locationKey) {
  if (cache.has(locationKey)) return cache.get(locationKey);

  const q = `[out:json][timeout:8];
way(around:100,${lat},${lon})["highway"]["name"];
out tags;`;

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 9000);

    const res  = await fetch(`${OVERPASS}?data=${encodeURIComponent(q)}`, { signal: controller.signal });
    clearTimeout(timer);
    const data = await res.json();

    const PRIORITY = {
      trunk: 0, primary: 1, primary_link: 2, secondary: 3,
      secondary_link: 4, tertiary: 5, residential: 6, unclassified: 7,
    };

    const ways = (data.elements || [])
      .filter(e => e.tags?.name)
      .sort((a, b) => {
        const pa = PRIORITY[a.tags.highway] ?? 99;
        const pb = PRIORITY[b.tags.highway] ?? 99;
        return pa - pb;
      });

    // De-duplicate names, keep top 4
    const names = [...new Map(ways.map(w => [w.tags.name, w.tags.highway])).entries()]
      .slice(0, 4)
      .map(([name, hw]) => ({ name, highway: hw }));

    cache.set(locationKey, names);
    return names;
  } catch (_) {
    cache.set(locationKey, []);
    return [];
  }
}

/**
 * Fetch road names for multiple locations in parallel.
 * @returns {Object} — { [location_key]: Array<{name, highway}> }
 */
export async function fetchAllRoadNames(locations) {
  const results = await Promise.allSettled(
    locations.map(loc =>
      fetchRoadNames(
        parseFloat(loc.latitude),
        parseFloat(loc.longitude),
        loc.location_key,
      )
    )
  );

  const map = {};
  locations.forEach((loc, i) => {
    const r = results[i];
    map[loc.location_key] = r.status === 'fulfilled' ? r.value : [];
  });
  return map;
}

/**
 * Compute the "most affected road" across the ranked hotspots.
 * Prefers the primary road at the #1 hotspot; falls back to highest frequency.
 */
export function getMostAffectedRoad(rankedLocs, roadNamesMap) {
  if (!rankedLocs.length) return null;

  const top1Names = roadNamesMap[rankedLocs[0]?.location_key] || [];
  const primaryCandidate = top1Names[0] || null;

  const freq = {};
  rankedLocs.forEach(loc => {
    (roadNamesMap[loc.location_key] || []).forEach(({ name }) => {
      freq[name] = (freq[name] || 0) + 1;
    });
  });

  if (!Object.keys(freq).length) return null;

  const sorted = Object.entries(freq).sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1];
    if (primaryCandidate && a[0] === primaryCandidate.name) return -1;
    if (primaryCandidate && b[0] === primaryCandidate.name) return  1;
    return 0;
  });

  const [winnerName, winnerCount] = sorted[0];
  const hw = rankedLocs
    .flatMap(loc => roadNamesMap[loc.location_key] || [])
    .find(r => r.name === winnerName)?.highway || 'road';

  return { name: winnerName, highway: hw, hotspotCount: winnerCount };
}

export function highwayLabel(hw) {
  const MAP = {
    trunk: 'Trunk Road', primary: 'Primary Road', primary_link: 'Primary Road',
    secondary: 'Secondary Road', secondary_link: 'Secondary Road',
    tertiary: 'Tertiary Road', residential: 'Local Road', unclassified: 'Local Road',
  };
  return MAP[hw] || 'Road';
}
