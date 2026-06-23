# Road Names Feature — Implementation Instructions
## Severity Heatmap: Show Affected Road Names Per Hotspot

Remove the synthetic corridor overlay. Replace with actual road names fetched from
OpenStreetMap, displayed as:
1. A permanent floating label on the map at each top-5 marker
2. Road names list inside every marker popup
3. Road names list on each EnforcementSidebar card
4. A "Most Affected Road" banner at the top of the enforcement panel

### Why the previous Overpass fetch was slow
The corridor feature asked Overpass for full road geometry (all node coordinates).
That response can be 40–100 KB per location, took 3–10 s each, ran sequentially.

This implementation asks Overpass only for **way tags** (`out tags;`) — no coordinates,
response is ~200 bytes per location, and all 5 requests fire **in parallel**.
Total fetch time: 1–3 s for all hotspots combined.

---

## STEP 1 — Create `frontend-react/src/utils/roadNameUtils.js`

This module handles fetching, caching, and computing "most affected road".

```js
const OVERPASS = 'https://overpass-api.de/api/interpreter';

// In-memory cache: location_key → string[]
// Persists for the lifetime of the page session — no redundant re-fetches.
const cache = new Map();

/**
 * Fetch road names (OSM way names) within 100 m of a point.
 * Returns up to 4 unique road names, sorted by highway class importance.
 * Uses tags-only query — response is ~200 bytes, not full geometry.
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

    // Priority order: trunk/primary > secondary > tertiary > residential > others
    const PRIORITY = { trunk: 0, primary: 1, primary_link: 2, secondary: 3,
                       secondary_link: 4, tertiary: 5, residential: 6, unclassified: 7 };

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
    // Timeout or Overpass unreachable — return empty so UI still works
    cache.set(locationKey, []);
    return [];
  }
}

/**
 * Fetch road names for multiple locations in parallel.
 * @param {Array} locations — prediction records with latitude, longitude, location_key
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
 * Compute the "most affected road" across all hotspots.
 * Definition: the road name that either
 *   (a) appears at the #1 ranked hotspot (priority), or
 *   (b) appears across the most hotspots (frequency fallback).
 *
 * @param {Array}  rankedLocs   — prediction records sorted by severity desc
 * @param {Object} roadNamesMap — output of fetchAllRoadNames
 * @returns {{ name: string, highway: string, hotspotCount: number } | null}
 */
export function getMostAffectedRoad(rankedLocs, roadNamesMap) {
  if (!rankedLocs.length) return null;

  // (a) If the #1 hotspot has a named road, use that as primary candidate
  const top1Names = roadNamesMap[rankedLocs[0]?.location_key] || [];
  const primaryCandidate = top1Names[0] || null;

  // (b) Count how many hotspots each road name appears in
  const freq = {};
  rankedLocs.forEach(loc => {
    const names = roadNamesMap[loc.location_key] || [];
    names.forEach(({ name }) => {
      freq[name] = (freq[name] || 0) + 1;
    });
  });

  if (!Object.keys(freq).length) return null;

  // Pick the road with the highest frequency; break ties by favouring primary candidate
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
```

---

## STEP 2 — Update `frontend-react/src/pages/SeverityPage.jsx`

Add two new pieces of state and a fetch effect. The page owns the road name data and
passes it down to both `HeatMap` and `EnforcementSidebar`.

### 2a — Add imports at the top

```js
import { fetchAllRoadNames, getMostAffectedRoad } from '../utils/roadNameUtils';
```

### 2b — Add state inside the component (after existing useState lines)

```js
const [roadNames,        setRoadNames]        = useState({});  // { location_key: [{name,highway}] }
const [mostAffectedRoad, setMostAffectedRoad] = useState(null);
const [roadNamesLoading, setRoadNamesLoading] = useState(false);
```

### 2c — Add a useEffect that fires when top5 changes

Add this after the existing `useEffect` blocks, before `handleRun`:

```js
// Fetch road names for top 5 severity hotspots in parallel
useEffect(() => {
  if (filteredPredictions.length === 0) {
    setRoadNames({});
    setMostAffectedRoad(null);
    return;
  }

  const key = scoreKey(selectedModel);
  const top5 = [...filteredPredictions]
    .sort((a, b) => (b[key] || 0) - (a[key] || 0))
    .slice(0, 5)
    .filter(p => p.latitude && p.longitude);

  setRoadNamesLoading(true);
  fetchAllRoadNames(top5).then(nameMap => {
    setRoadNames(nameMap);
    setMostAffectedRoad(getMostAffectedRoad(top5, nameMap));
    setRoadNamesLoading(false);
  });
}, [filteredPredictions, selectedModel]);
```

### 2d — Pass the new props to HeatMap and EnforcementSidebar

In the return JSX, update the two component usages:

**HeatMap** — add `roadNames` prop:
```jsx
<HeatMap
  predictions={filteredPredictions}
  selectedModel={selectedModel}
  colorScheme="severity"
  displayTopN={DISPLAY_TOP_N}
  roadNames={roadNames}              {/* ADD */}
/>
```

**EnforcementSidebar** — add `roadNames` and `mostAffectedRoad` props:
```jsx
<EnforcementSidebar
  predictions={filteredPredictions}
  selectedModel={selectedModel}
  colorScheme="severity"
  showSeverityFields={true}
  persistenceScores={persistenceScores}
  selectedStation={selectedStation}
  roadNames={roadNames}              {/* ADD */}
  mostAffectedRoad={mostAffectedRoad}  {/* ADD */}
  roadNamesLoading={roadNamesLoading}  {/* ADD */}
/>
```

---

## STEP 3 — Update `frontend-react/src/components/HeatMap.jsx`

### 3a — Remove the synthetic corridor code

Delete the block at the top of the file (lines 10–30) that contains:
```js
const ARM_M   = 180;
const LAT_DEG = ARM_M / 111000;
const LON_DEG = ARM_M / 108200;
function buildCorridorArms(lat, lon) { ... }
```

Also delete the entire second `useEffect` that draws corridors (the one that checks
`colorScheme !== 'severity'` and calls `buildCorridorArms`). Delete the
`const roadLayer = useRef(null);` line too.

### 3b — Update the component signature to accept `roadNames`

```js
const HeatMap = ({ predictions, selectedModel, colorScheme, displayTopN = 500, roadNames = {} }) => {
```

### 3c — Add permanent road name tooltips for top-5 markers

Inside the marker loop (the `sorted.slice(0, displayTopN).forEach(...)` block),
**after** the `marker.bindPopup(...)` line, add:

```js
// Permanent road name label for top-5 severity hotspots
if (colorScheme === 'severity' && rank <= 5) {
  const locRoads = roadNames[loc.location_key];
  if (locRoads && locRoads.length > 0) {
    const primaryRoad = locRoads[0].name;
    marker.bindTooltip(primaryRoad, {
      permanent: true,
      direction: 'top',
      offset: [0, rank <= 3 ? -14 : -10],
      className: `road-name-label ${rank === 1 ? 'road-label-rank1' : ''}`,
    });
  }
}
```

**Important:** This tooltip code must be inside the same `useEffect` that renders
markers, so road name labels rebuild whenever `roadNames` changes. Add `roadNames`
to that useEffect's dependency array:

```js
}, [predictions, selectedModel, colorScheme, roadNames]);
//                                                ^^^ add this
```

### 3d — Update `buildPopup` to include road names

Inside `buildPopup`, in the `isSev` branch, after the `sev-narrative-box` block,
add road name rows. The function needs to accept `roadNames` as a parameter.

**Update the function signature:**
```js
function buildPopup(loc, rank, model, score, logRatio, colorFn, colorScheme, roadNames = {}) {
```

**Update the call site** (find `marker.bindPopup(buildPopup(...))`):
```js
marker.bindPopup(
  buildPopup(loc, rank, selectedModel, score, logRatio, colorFn, colorScheme, roadNames),
  { maxWidth: 320 }
);
```

**Add the road name rows inside `buildPopup`**, in the `isSev` branch,
after the existing `sev-narrative-box` HTML and before `sev-details-grid`:

```js
// Road names section
const locRoads = roadNames[loc.location_key] || [];
const roadRowsHtml = locRoads.length > 0
  ? `<div class="popup-road-names">
       <div class="prn-label">Affected Roads</div>
       ${locRoads.map((r, i) => `
         <div class="prn-row ${i === 0 ? 'prn-primary' : ''}">
           <span class="prn-dot"></span>
           <span class="prn-name">${escH(r.name)}</span>
           <span class="prn-hw">${highwayLabel(r.highway)}</span>
         </div>`).join('')}
     </div>`
  : '';
```

Then insert `${roadRowsHtml}` into the returned HTML string, between the
`sev-narrative-box` section and the `sev-details-grid` section.

You also need to import `highwayLabel` at the top of `HeatMap.jsx`:
```js
import { getSeverityNarrative } from '../utils/severityUtils';
import { highwayLabel } from '../utils/roadNameUtils';   // ADD
```

---

## STEP 4 — Update `frontend-react/src/components/EnforcementSidebar.jsx`

### 4a — Update props signature

```js
export default function EnforcementSidebar({
  predictions, selectedModel, colorScheme, showSeverityFields,
  persistenceScores = {}, selectedStation = '',
  roadNames = {},          // ADD
  mostAffectedRoad = null, // ADD
  roadNamesLoading = false, // ADD
}) {
```

### 4b — Add "Most Affected Road" banner at top of `.es-body`

Immediately inside `<div className="es-body">`, before the empty-state check:

```jsx
{/* Most Affected Road banner — only on severity page */}
{showSeverityFields && (mostAffectedRoad || roadNamesLoading) && (
  <div className="es-most-affected-road">
    <div className="emar-label">
      <span className="emar-icon">🛣</span>
      Most Affected Road
    </div>
    {roadNamesLoading ? (
      <div className="emar-loading">Identifying roads…</div>
    ) : (
      <>
        <div className="emar-road-name">{mostAffectedRoad.name}</div>
        <div className="emar-meta">
          {highwayLabel(mostAffectedRoad.highway)}
          {' · '}
          Affects {mostAffectedRoad.hotspotCount} of top-5 hotspots
        </div>
      </>
    )}
  </div>
)}
```

Add `import { highwayLabel } from '../utils/roadNameUtils';` at the top of EnforcementSidebar.jsx.

### 4c — Add road names to each top-3 card

Inside the `top10.slice(0, 3).map(...)` block, after the `showSeverityFields` block
(or after the risk bar), add:

```jsx
{showSeverityFields && (() => {
  const locRoads = roadNames[pred.location_key] || [];
  if (!locRoads.length) return null;
  return (
    <div className="es-road-names">
      <div className="es-rn-header">Affected Roads</div>
      {locRoads.map((r, i) => (
        <div key={r.name} className={`es-rn-row ${i === 0 ? 'es-rn-primary' : ''}`}>
          <span className="es-rn-dot" />
          <span className="es-rn-name">{r.name}</span>
          <span className="es-rn-hw">{highwayLabel(r.highway)}</span>
        </div>
      ))}
    </div>
  );
})()}
```

### 4d — Add road name sub-label to compact list items (ranks 4–10)

In the compact list `li` render, after `.es-compact-name`, add:

```jsx
{showSeverityFields && (() => {
  const roads = roadNames[pred.location_key];
  return roads?.[0]
    ? <span className="es-compact-road">{roads[0].name}</span>
    : null;
})()}
```

---

## STEP 5 — CSS Additions

### Add to `HeatMap.css`

```css
/* ── Permanent road name tooltip labels ── */
.road-name-label {
  background: rgba(255, 255, 255, 0.92) !important;
  border: 1px solid #e5e7eb !important;
  border-radius: 5px !important;
  padding: 3px 7px !important;
  font-size: 11px !important;
  font-weight: 700 !important;
  color: #1f2937 !important;
  white-space: nowrap !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.12) !important;
  pointer-events: none !important;
}

/* Rank 1 label — slightly larger and amber-accented */
.road-label-rank1 {
  background: #fffbeb !important;
  border-color: #fbbf24 !important;
  font-size: 12px !important;
  color: #92400e !important;
}

/* Remove the default leaflet tooltip arrow */
.road-name-label::before { display: none !important; }

/* ── Road names inside popup ── */
.popup-road-names {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 7px;
  padding: 8px 10px;
  margin: 8px 0;
}

.prn-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #6b7280;
  margin-bottom: 6px;
}

.prn-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 3px 0;
  font-size: 12px;
  color: #374151;
}

.prn-primary {
  font-weight: 700;
  color: #1f2937;
}

.prn-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9ca3af;
  flex-shrink: 0;
}

.prn-primary .prn-dot {
  background: #6366f1;
  width: 8px;
  height: 8px;
}

.prn-name { flex: 1; }

.prn-hw {
  font-size: 10px;
  color: #9ca3af;
  font-weight: 500;
  white-space: nowrap;
}
```

### Add to `EnforcementSidebar.css`

```css
/* ── Most Affected Road banner ── */
.es-most-affected-road {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 4px;
}

.emar-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: #94a3b8;
  margin-bottom: 8px;
}

.emar-icon { font-size: 13px; }

.emar-road-name {
  font-size: 17px;
  font-weight: 800;
  color: #f1f5f9;
  line-height: 1.2;
  margin-bottom: 5px;
}

.emar-meta {
  font-size: 11px;
  color: #64748b;
  font-weight: 500;
}

.emar-loading {
  font-size: 12px;
  color: #64748b;
  font-style: italic;
}

/* ── Road names inside enforcement cards ── */
.es-road-names {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 6px 0;
}

.es-rn-header {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #6b7280;
  margin-bottom: 5px;
}

.es-rn-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 2px 0;
  font-size: 12px;
  color: #374151;
}

.es-rn-primary {
  font-weight: 700;
  color: #1f2937;
}

.es-rn-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d1d5db;
  flex-shrink: 0;
}

.es-rn-primary .es-rn-dot {
  background: #f59e0b;
  width: 8px;
  height: 8px;
}

.es-rn-name { flex: 1; }

.es-rn-hw {
  font-size: 10px;
  color: #9ca3af;
}

/* ── Road name in compact list ── */
.es-compact-road {
  display: block;
  font-size: 10px;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 1px;
}
```

---

## STEP 6 — Verify

1. Run Severity Heatmap → Run Prediction
2. Markers appear **instantly** (road names fetch is non-blocking)
3. Within 1–3 s, permanent labels appear above the top-5 markers (e.g., "Hosur Road")
4. The rank-1 marker's label is slightly larger with an amber tint
5. Click any top-5 marker → popup shows "Affected Roads" list with the primary road in bold
6. Enforcement sidebar → dark banner at top shows "Most Affected Road: Hosur Road · Primary Road · Affects 3 of top-5 hotspots"
7. Each top-3 card shows its road names list
8. Compact list (ranks 4–10) shows the primary road name as a grey sub-label
9. Switch to Count Heatmap → no road labels, no banner (road features are severity-only)
10. If Overpass times out → UI still works, no road names appear, no error shown

---

## WHAT AN OFFICER SEES

**Before:** Red dot at BGS Flyover. Score: 9.4.

**After:**
- Floating label on the map: **"Mysore Road"** (permanent, always visible)
- Dark banner in sidebar: 🛣 Most Affected Road → **Mysore Road** · Primary Road · Affects 4 of top-5 hotspots
- Click the marker → popup lists:
  - **Mysore Road** (Primary Road) ← bold, this is the one causing the blockage
  - Ring Road (Secondary Road)
  - Service Road (Local Road)
- Card in enforcement panel: "Affected Roads: Mysore Road, Ring Road"

The officer now knows: **this is a Mysore Road problem**, not just a coordinate.
