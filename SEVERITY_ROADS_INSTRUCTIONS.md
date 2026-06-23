# Severity Heatmap Enhancement Instructions
## Feature: Human-Readable Severity Reason + Road Segment Highlighting

Two new capabilities for the Severity Heatmap, designed for traffic officers:
1. **Plain-English severity reason** — every hotspot explains *why* it's severe,
   using vehicle type, PCU weight, and lane count in officer-readable language.
2. **Road segment highlighting** — the actual road(s) affected by each top-10
   hotspot are drawn as colored polylines on the Leaflet map, so officers immediately
   see which carriageway is blocked, not just a dot.

---

## PART 1 — Severity Narrative Utility

### Step 1.1 — Create `frontend-react/src/utils/severityUtils.js`

This file is the single source of truth for generating officer-friendly severity text.
It uses real PCU weights from `pcu_weights.json` (IRC SP-41-1994 standard).

```js
// PCU (Passenger Car Unit) factors — from prediction_api/models/pcu_weights.json
// These tell us how much road space each vehicle type occupies vs. a car
const PCU = {
  two_wheeler:   0.5,
  auto_rickshaw: 1.2,
  car:           1.0,
  lcv:           1.5,
  bus:           2.5,
  heavy_truck:   3.0,
  tractor:       4.0,
};

const VEH_LABEL = {
  two_wheeler:   'two-wheelers',
  auto_rickshaw: 'auto-rickshaws',
  car:           'cars',
  lcv:           'light commercial vehicles',
  bus:           'buses',
  heavy_truck:   'heavy trucks',
  tractor:       'tractors',
};

const VEH_EMOJI = {
  two_wheeler:   '🛵',
  auto_rickshaw: '🛺',
  car:           '🚗',
  lcv:           '🚐',
  bus:           '🚌',
  heavy_truck:   '🚛',
  tractor:       '🚜',
};

/**
 * Generates a plain-English explanation of why a location has a high severity score.
 * Written at the level a traffic officer would understand immediately.
 *
 * @param {object} pred — a severity prediction record from /api/v1/traffic-severity/predict
 * @returns {{ headline: string, detail: string, emoji: string, blockagePct: number }}
 */
export function getSeverityNarrative(pred) {
  const vehicleCat  = pred.dominant_vehicle_cat;
  const laneCount   = pred.lane_count != null ? parseFloat(pred.lane_count) : null;
  const violation   = pred.dominant_violation;
  const score       = pred.lightgbm_prediction || 0;

  const pcu      = PCU[vehicleCat] || 1.0;
  const emoji    = VEH_EMOJI[vehicleCat] || '🚗';
  const vehLabel = VEH_LABEL[vehicleCat] || 'vehicles';

  // Blockage ratio: how much of the road width does this vehicle occupy?
  // A heavy truck (3 PCU) on a 2-lane road = 150% → full blockage
  const blockagePct = laneCount && laneCount > 0
    ? Math.min(100, Math.round((pcu / laneCount) * 100))
    : Math.min(100, Math.round(pcu * 40));   // fallback when lane data absent

  // --- Headline: short, punchy, designed for the sidebar card ---
  let headline;
  if (blockagePct >= 90) {
    headline = `${emoji} Full carriageway blocked by ${vehLabel}`;
  } else if (blockagePct >= 60) {
    headline = `${emoji} ${blockagePct}% of road blocked by ${vehLabel}`;
  } else if (blockagePct >= 35) {
    headline = `${emoji} Partial blockage — ${vehLabel} spilling onto road`;
  } else {
    headline = `${emoji} Recurring ${vehLabel} spillover`;
  }

  // --- Detail: one sentence for the popup / drawer ---
  let detail = '';

  // Vehicle + lane context
  if (laneCount != null) {
    const laneWord = laneCount <= 1 ? 'single-lane' : `${Math.round(laneCount)}-lane`;
    if (blockagePct >= 90) {
      detail += `A ${vehLabel.replace(/s$/, '')} (${pcu} PCU) on this ${laneWord} road leaves no room for other traffic. `;
    } else {
      detail += `${capitalize(vehLabel)} (${pcu} PCU each) reduce usable width on this ${laneWord} road by ~${blockagePct}%. `;
    }
  } else {
    detail += `${capitalize(vehLabel)} are the primary offenders at this location. `;
  }

  // Violation type context
  if (violation && violation.toLowerCase() !== 'unknown') {
    detail += `Most common violation: "${violation}". `;
  }

  // Score-based urgency
  if (score >= 8) {
    detail += 'Immediate enforcement needed — this junction has critical impact on network flow.';
  } else if (score >= 4) {
    detail += 'Elevated impact — peak-hour patrol recommended.';
  } else {
    detail += 'Monitor during peak hours.';
  }

  return { headline, detail, emoji, blockagePct };
}

/**
 * Short label for compact list items (EnforcementSidebar ranks 4–10).
 */
export function getSeverityShortLabel(pred) {
  const vehicleCat = pred.dominant_vehicle_cat;
  const laneCount  = pred.lane_count;
  const pcu        = PCU[vehicleCat] || 1.0;
  const veh        = VEH_LABEL[vehicleCat] || 'vehicles';
  const pct        = laneCount
    ? Math.min(100, Math.round((pcu / laneCount) * 100))
    : null;
  return pct != null ? `${pct}% blockage · ${veh}` : veh;
}

function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
}
```

---

## PART 2 — Road Segment Highlighting Inside HeatMap.jsx

The plan: when `colorScheme === 'severity'`, fetch road geometries from the
**Overpass API** (free, no auth, uses OpenStreetMap data) for the top 10 severity
locations and draw colored Leaflet polylines over the map tiles.

Each polyline:
- Is **colored** using the same `sevRiskColor()` scale as the markers
- Has **width** proportional to severity (4 px low → 12 px critical)
- Has a **glow layer** (wider, semi-transparent polyline underneath for visual punch)
- Shows a **popup** with the severity narrative on click
- Is on a **separate layer group** so it can be added/removed independently of markers

### Step 2.1 — Add the Overpass fetch helpers to HeatMap.jsx

Add these functions at the **top of HeatMap.jsx**, just before the `HeatMap` component definition:

```js
// ── Road geometry helpers (severity view only) ────────────────────────────────

const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';

/**
 * Fetch all road ways within 80 m of a point.
 * Returns parsed Overpass JSON, or null on failure.
 */
async function fetchRoadGeometry(lat, lon) {
  // Only fetch primary/secondary/tertiary/residential roads — skip footpaths etc.
  const query = `[out:json][timeout:15];
way(around:80,${lat},${lon})["highway"~"^(primary|secondary|tertiary|residential|trunk|unclassified|primary_link|secondary_link)$"];
(._;>;);
out body;`;

  const res = await fetch(`${OVERPASS_URL}?data=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error(`Overpass ${res.status}`);
  return res.json();
}

/**
 * Parse Overpass response into arrays of [lat, lon] coordinate pairs — one per way.
 * Returns [] if parsing fails or no ways found.
 */
function parseWayCoordinates(data) {
  if (!data?.elements) return [];

  // Build node id → [lat, lon] lookup
  const nodeMap = {};
  data.elements.forEach(el => {
    if (el.type === 'node') nodeMap[el.id] = [el.lat, el.lon];
  });

  const ways = [];
  data.elements.forEach(el => {
    if (el.type !== 'way' || !el.nodes) return;
    const coords = el.nodes.map(id => nodeMap[id]).filter(Boolean);
    if (coords.length >= 2) {
      ways.push({
        coords,
        name: el.tags?.name || el.tags?.['name:en'] || null,
        highway: el.tags?.highway || 'road',
      });
    }
  });
  return ways;
}

/**
 * Build a human-readable road classification label for the popup.
 */
function roadClassLabel(highway) {
  const MAP = {
    primary: 'Primary Road', secondary: 'Secondary Road',
    tertiary: 'Tertiary Road', residential: 'Residential Road',
    trunk: 'Trunk Road', unclassified: 'Local Road',
    primary_link: 'Primary Link', secondary_link: 'Secondary Link',
  };
  return MAP[highway] || 'Road';
}
```

### Step 2.2 — Add a second `useEffect` for road highlighting in the `HeatMap` component

Add this **after** the existing marker `useEffect` (the one that sets `markerLayer.current`),
still inside the `HeatMap` component body:

```js
// ── Road highlighting (severity view only) ────────────────────────────────────
const roadLayer   = useRef(null);
const abortFlag   = useRef(false);   // lets us cancel an in-flight fetch sequence

useEffect(() => {
  const m = leafletMap.current;
  if (!m) return;

  // Clean up previous road overlay
  abortFlag.current = true;                           // cancel any running fetch loop
  if (roadLayer.current) {
    m.removeLayer(roadLayer.current);
    roadLayer.current = null;
  }

  // Only run in severity mode with data
  if (colorScheme !== 'severity' || !predictions || predictions.length === 0) return;

  const key     = scoreKey(selectedModel);
  const sorted  = [...predictions]
    .sort((a, b) => (b[key] || 0) - (a[key] || 0))
    .filter(p => !isNaN(parseFloat(p.latitude)) && !isNaN(parseFloat(p.longitude)));

  const top10   = sorted.slice(0, 10);
  const maxScore = Math.max(...sorted.map(p => p[key] || 0), 1e-6);

  const layer = L.layerGroup();
  roadLayer.current = layer;
  layer.addTo(m);
  abortFlag.current = false;  // fresh run

  // Sequential fetch — Overpass allows ~1 req/sec for free tier
  const runFetch = async () => {
    for (let i = 0; i < top10.length; i++) {
      if (abortFlag.current) return;

      const loc   = top10[i];
      const lat   = parseFloat(loc.latitude);
      const lon   = parseFloat(loc.longitude);
      const score = loc[key] || 0;
      const ratio = score / maxScore;
      const color = sevRiskColor(ratio);

      // Stroke width: 4 px at lowest severity, up to 12 px at maximum
      const weight = Math.round(4 + ratio * 8);

      try {
        const data = await fetchRoadGeometry(lat, lon);
        if (abortFlag.current) return;

        const ways = parseWayCoordinates(data);

        ways.forEach(({ coords, name, highway }) => {
          // Glow layer — wider, more transparent, drawn first (below)
          L.polyline(coords, {
            color,
            weight: weight + 8,
            opacity: 0.18,
            lineCap: 'round',
            lineJoin: 'round',
          }).addTo(layer);

          // Main colored road line
          const pl = L.polyline(coords, {
            color,
            weight,
            opacity: ratio > 0.6 ? 0.88 : 0.72,
            lineCap: 'round',
            lineJoin: 'round',
            className: i < 3 ? 'sev-road-critical' : '',   // CSS pulse for top 3
          });

          // Popup: severity narrative + road name
          const { headline, detail, blockagePct } = getSeverityNarrative(loc);
          const roadName = name ? `<strong>${escH(name)}</strong>` : roadClassLabel(highway);
          pl.bindPopup(`
            <div class="sev-road-popup">
              <div class="srp-road-label">🛣 ${roadName}</div>
              <div class="srp-headline">${escH(headline)}</div>
              <div class="srp-detail">${escH(detail)}</div>
              <div class="srp-score-row">
                <span class="srp-dot" style="background:${color}"></span>
                <span>Severity score: <strong>${score.toFixed(2)}</strong> · ${blockagePct}% blockage</span>
              </div>
              <a class="srp-maps-link"
                 href="https://maps.google.com/?q=${lat},${lon}"
                 target="_blank" rel="noreferrer">
                Open in Google Maps →
              </a>
            </div>
          `, { maxWidth: 300 });

          layer.addLayer(pl);
        });

      } catch (_) {
        // Overpass unavailable or timed out — silently skip; markers still show
      }

      // Respect Overpass free-tier rate limit
      if (i < top10.length - 1) {
        await new Promise(r => setTimeout(r, 500));
      }
    }
  };

  runFetch();

  return () => { abortFlag.current = true; };

}, [predictions, selectedModel, colorScheme]);
```

### Step 2.3 — Import `getSeverityNarrative` at the top of HeatMap.jsx

Add to the existing imports line:
```js
import { getSeverityNarrative } from '../utils/severityUtils';
```

Keep all existing imports intact.

### Step 2.4 — Update `buildPopup` to use the narrative (severity mode)

Inside `buildPopup`, find the `sevFields` block (around line 185–200).
Replace the whole `sevFields` construction with:

```js
let sevFields = '';
if (isSev) {
  const { headline, detail, blockagePct } = getSeverityNarrative(loc);

  const VEH = {
    two_wheeler:'two-wheelers', auto_rickshaw:'auto-rickshaws', car:'cars',
    lcv:'light commercial vehicles', bus:'buses', heavy_truck:'heavy trucks', tractor:'tractors',
  };
  const lane     = loc.lane_count != null ? loc.lane_count.toFixed(1) : '—';
  const vehLabel = VEH[loc.dominant_vehicle_cat] || (loc.dominant_vehicle_cat || '—');
  const vioType  = loc.dominant_violation || '—';
  const laneNum  = loc.lane_count != null ? Math.round(loc.lane_count) : null;
  const laneWord = laneNum != null ? (laneNum <= 1 ? 'single-lane' : `${laneNum}-lane`) : '';

  // Blockage bar color
  const barColor = blockagePct >= 80 ? '#ef4444' : blockagePct >= 50 ? '#f59e0b' : '#22c55e';

  sevFields = `
    <div class="sev-narrative-box">
      <div class="sev-narrative-headline">${escH(headline)}</div>
      <div class="sev-narrative-detail">${escH(detail)}</div>
      <div class="sev-blockage-bar-wrap">
        <div class="sev-blockage-bar-track">
          <div class="sev-blockage-bar-fill"
               style="width:${blockagePct}%;background:${barColor}"></div>
        </div>
        <span class="sev-blockage-label">${blockagePct}% carriageway blocked</span>
      </div>
    </div>
    <div class="sev-details-grid">
      <div class="sev-detail-item">
        <span class="sev-detail-label">Lane count</span>
        <span class="sev-detail-val">${escH(lane)}</span>
      </div>
      <div class="sev-detail-item">
        <span class="sev-detail-label">Vehicle type</span>
        <span class="sev-detail-val">${escH(vehLabel)}</span>
      </div>
      <div class="sev-detail-item sev-detail-wide">
        <span class="sev-detail-label">Common violation</span>
        <span class="sev-detail-val">${escH(vioType)}</span>
      </div>
    </div>`;
} else {
  sevFields = `
    <div class="count-explainer">
      <span>📍</span>
      <em>Predicted illegal parking events at this location</em>
    </div>`;
}
```

---

## PART 3 — Severity Reason Badge in EnforcementSidebar

### Step 3.1 — Import `getSeverityNarrative` in EnforcementSidebar.jsx

```js
import { getSeverityNarrative } from '../utils/severityUtils';
```

### Step 3.2 — Add the badge inside each top-3 card

Inside the `.map((pred, idx) => { ... })` that renders the top-3 cards,
after the `.es-stats-row` div and before the existing `showSeverityFields` block,
add:

```jsx
{/* Severity narrative — only on severity page */}
{showSeverityFields && (() => {
  const { headline, detail, blockagePct } = getSeverityNarrative(pred);
  const barColor = blockagePct >= 80 ? '#ef4444' : blockagePct >= 50 ? '#f59e0b' : '#22c55e';
  return (
    <div className="es-severity-reason">
      <div className="es-severity-headline">{headline}</div>
      <div className="es-severity-detail">{detail}</div>
      <div className="es-severity-bar-wrap">
        <div className="es-severity-bar-track">
          <div
            className="es-severity-bar-fill"
            style={{ width: `${blockagePct}%`, background: barColor }}
          />
        </div>
        <span className="es-severity-bar-label">{blockagePct}% carriageway</span>
      </div>
    </div>
  );
})()}
```

### Step 3.3 — Add short label to compact list items (ranks 4–10)

Import `getSeverityShortLabel` in EnforcementSidebar.jsx:
```js
import { getSeverityNarrative, getSeverityShortLabel } from '../utils/severityUtils';
```

In the compact list `li` render, after `.es-compact-name`, add:
```jsx
{showSeverityFields && pred.dominant_vehicle_cat && (
  <span className="es-compact-severity-sub">
    {getSeverityShortLabel(pred)}
  </span>
)}
```

---

## PART 4 — CSS

### Step 4.1 — Add to `HeatMap.css`

```css
/* ── Road highlighting polylines ── */

/* Pulsing outline for the 3 most critical roads */
.sev-road-critical {
  animation: road-pulse 2.5s ease-in-out infinite;
}

@keyframes road-pulse {
  0%, 100% { stroke-opacity: 0.88; }
  50%       { stroke-opacity: 0.45; }
}

/* Road popup */
.sev-road-popup {
  padding: 14px 16px;
  min-width: 240px;
}

.srp-road-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.srp-headline {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-main);
  margin-bottom: 6px;
  line-height: 1.35;
}

.srp-detail {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.55;
  margin-bottom: 10px;
}

.srp-score-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.srp-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.srp-maps-link {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  color: #6366f1;
  text-decoration: none;
}
.srp-maps-link:hover { text-decoration: underline; }

/* ── Severity narrative inside marker popup ── */

.sev-narrative-box {
  background: #fef9ec;
  border: 1px solid #fbbf24;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 10px 0 8px;
}

.sev-narrative-headline {
  font-size: 13px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 5px;
  line-height: 1.3;
}

.sev-narrative-detail {
  font-size: 12px;
  color: #78350f;
  line-height: 1.55;
  margin-bottom: 8px;
}

.sev-blockage-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sev-blockage-bar-track {
  flex: 1;
  height: 5px;
  background: #fde68a;
  border-radius: 3px;
  overflow: hidden;
}

.sev-blockage-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s;
}

.sev-blockage-label {
  font-size: 10px;
  font-weight: 700;
  color: #92400e;
  white-space: nowrap;
}
```

### Step 4.2 — Add to `EnforcementSidebar.css`

```css
/* Severity reason block inside enforcement card */
.es-severity-reason {
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 8px 0;
}

.es-severity-headline {
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 4px;
  line-height: 1.3;
}

.es-severity-detail {
  font-size: 11px;
  color: #78350f;
  line-height: 1.5;
  margin-bottom: 8px;
}

.es-severity-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.es-severity-bar-track {
  flex: 1;
  height: 4px;
  background: #fde68a;
  border-radius: 2px;
  overflow: hidden;
}

.es-severity-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s;
}

.es-severity-bar-label {
  font-size: 10px;
  font-weight: 700;
  color: #92400e;
  white-space: nowrap;
}

/* Short sub-label in compact list */
.es-compact-severity-sub {
  font-size: 10px;
  color: var(--text-muted);
  display: block;
  margin-top: 1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

---

## PART 5 — Legend: Tell Officers What the Road Colors Mean

Add a compact legend overlay to the map in **severity mode only**.
Inside `HeatMap.jsx`, update the return JSX:

```jsx
return (
  <div className="heatmap-wrapper">
    <div ref={mapRef} className="heatmap-leaflet" />
    {colorScheme === 'severity' && (
      <div className="sev-road-legend">
        <div className="srl-title">Road Blockage</div>
        <div className="srl-row"><span className="srl-swatch" style={{background:'#ef4444'}} />Critical</div>
        <div className="srl-row"><span className="srl-swatch" style={{background:'#f59e0b'}} />Elevated</div>
        <div className="srl-row"><span className="srl-swatch" style={{background:'#10b981'}} />Moderate</div>
        <div className="srl-note">Roads highlighted for top-10 hotspots</div>
      </div>
    )}
  </div>
);
```

Add to `HeatMap.css`:
```css
.sev-road-legend {
  position: absolute;
  bottom: 48px;
  left: 12px;
  background: rgba(255,255,255,0.95);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  pointer-events: none;
}

.srl-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.srl-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 4px;
}

.srl-swatch {
  width: 24px;
  height: 5px;
  border-radius: 3px;
  display: inline-block;
}

.srl-note {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 5px;
  font-style: italic;
}
```

---

## PART 6 — Verification Checklist

After implementing all steps, verify:

1. **Switch to Severity Heatmap** → Run Prediction
2. **Map:** Within ~5 seconds of predictions loading, colored road lines appear
   over the carrier roads near each top-10 hotspot. Wider and redder = more severe.
3. **Click a colored road line** → popup appears with:
   - Road name (from OSM) or road class
   - Headline: e.g., "🚛 Full carriageway blocked by heavy trucks"
   - Detail sentence: lanes, PCU, violation type, urgency level
   - Blockage % score
   - "Open in Google Maps →" link
4. **Click a marker popup** → same narrative appears in the amber box
5. **Enforcement sidebar** → each of the top-3 cards has an amber box below
   the stats row with the headline, detail, and blockage bar
6. **Compact list (ranks 4–10)** → each item shows a sub-label like "75% blockage · heavy trucks"
7. **Legend** → bottom-left corner of map shows "Road Blockage" with red/amber/green swatches
8. **Switch back to Count Heatmap** → road polylines disappear, legend disappears,
   count mode works exactly as before

---

## GRACEFUL DEGRADATION

The Overpass API is a free public service. If it's slow or unreachable:
- The `try/catch` in the fetch loop silently skips failed locations
- Markers still appear and the narrative still shows in popups (it's computed client-side)
- Road lines are "nice to have" — the core enforcement data works without them
- The `abortFlag` ensures no memory leaks if the user switches pages mid-fetch

---

## HOW OFFICERS READ THIS

**Before:** Map shows a red dot at Silk Board. Number: 9.4. Officer: "OK, something's wrong here."

**After:**
- Map shows a thick red line along Hosur Road at Silk Board
- Click the line → "🚛 Full carriageway blocked by heavy trucks"
- Detail → "A heavy truck (3.0 PCU) on this 2-lane road leaves no room for other traffic.
  Most common violation: 'No Parking'. Immediate enforcement needed."
- Enforcement sidebar → same headline in amber box, blockage bar showing 90%

The officer now knows: **which road, what vehicle, how bad, and what to do.**
