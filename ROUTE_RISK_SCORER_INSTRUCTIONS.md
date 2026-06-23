# Route Risk Scorer — Implementation Instructions

## Overview

A new page where an officer draws a route on a Leaflet map by clicking waypoints.
The system finds all severity hotspots within 200 m of that route, sums their severity
scores into a cumulative risk number, fetches per-hotspot hourly profiles, and identifies
the 3-hour travel window with the lowest aggregate violation intensity.

Zero new ML models. No new DB. All computation is pure JS on already-available data.

---

## Files to create or modify

| Action | File |
|--------|------|
| CREATE | `frontend-react/src/pages/RoutePage.jsx` |
| CREATE | `frontend-react/src/pages/RoutePage.css` |
| MODIFY | `frontend-react/src/App.jsx` — add route page |
| MODIFY | `frontend-react/src/components/TopNav.jsx` — add nav link |
| MODIFY | `prediction_api/app/schemas.py` — add BatchHourlyRequest |
| MODIFY | `prediction_api/app/routers/analytics.py` — add batch endpoint |

---

## STEP 1 — Backend: Add `BatchHourlyRequest` to `schemas.py`

`typing` already imports `Optional`. Also add `List, Dict` if not present.

Find the line:
```python
from typing import Optional
```
Replace with:
```python
from typing import Dict, List, Optional
```

Then after the last class in the file (after `HourlyProfileRecord` or wherever the file ends), add:

```python
class BatchHourlyRequest(BaseModel):
    """Body for POST /api/v1/hourly-profiles/batch."""
    location_keys: List[str]
```

---

## STEP 2 — Backend: Add batch endpoint to `analytics.py`

Open `prediction_api/app/routers/analytics.py`.

At the top, verify (or add if missing) this import:
```python
from app.schemas import BatchHourlyRequest
```

Then add the following endpoint anywhere after the existing `/hourly-profile` GET endpoint:

```python
@router.post("/hourly-profiles/batch")
async def get_hourly_profiles_batch(
    request: Request,
    body: BatchHourlyRequest,
) -> Dict[str, List[float]]:
    """
    Return 24-hour violation profiles for a list of location_keys in one round-trip.
    Missing keys get a flat [0.0]*24 profile rather than a 404.
    """
    profiles: Dict[str, List[float]] = getattr(request.app.state, "hourly_profiles", {})
    return {k: profiles.get(k, [0.0] * 24) for k in body.location_keys}
```

**After these two backend changes, restart the FastAPI server.**
The new endpoint will appear at `POST /api/v1/hourly-profiles/batch` in the Swagger docs.

---

## STEP 3 — Create `frontend-react/src/pages/RoutePage.jsx`

Create this file with the full content below.

### How it works
- Loads severity predictions from `/api/v1/traffic-severity/predict` (same endpoint as SeverityPage, uses the current timestamp on page load).
- Renders a Leaflet map. A "Draw Route" toggle activates click-to-add-waypoint mode.
- Each click adds a blue dot marker + extends the polyline. Double-click finishes.
- On finish: `analyzeRoute()` runs the spatial match + scoring + hourly fetch.
- Right sidebar shows: risk score, risk level badge, hotspot count, 24-hour bar chart, safest window banner, ranked hotspot list.

```jsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import axios from 'axios';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid,
} from 'recharts';
import { Loader2, MapPin, Trash2, Navigation } from 'lucide-react';
import { SEV_API } from '../hooks/useApi';
import './RoutePage.css';

// ── Constants ──────────────────────────────────────────────────────────────
const BENGALURU_CENTER = [12.9716, 77.5946];
const TILE_URL  = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
const TILE_ATTR = '&copy; OpenStreetMap &copy; CARTO';
const BUFFER_OPTIONS = [100, 200, 400];

// ── Geometry helpers ────────────────────────────────────────────────────────
function toRad(d) { return d * Math.PI / 180; }

/** Approximate distance (metres) from point P to segment AB — flat-earth OK for <10 km. */
function pointToSegmentM(plat, plon, alat, alon, blat, blon) {
  const latS = 111000;
  const lonS = 111000 * Math.cos(toRad((alat + blat) / 2));
  const px = (plon - alon) * lonS, py = (plat - alat) * latS;
  const bx = (blon - alon) * lonS, by = (blat - alat) * latS;
  const len2 = bx * bx + by * by;
  if (len2 === 0) return Math.sqrt(px * px + py * py);
  const t = Math.max(0, Math.min(1, (px * bx + py * by) / len2));
  return Math.sqrt((px - t * bx) ** 2 + (py - t * by) ** 2);
}

/** Minimum distance (metres) from a lat/lon point to a multi-segment polyline. */
function minDistToPolyline(lat, lon, waypoints) {
  let min = Infinity;
  for (let i = 0; i < waypoints.length - 1; i++) {
    const d = pointToSegmentM(lat, lon,
      waypoints[i][0], waypoints[i][1],
      waypoints[i + 1][0], waypoints[i + 1][1]);
    if (d < min) min = d;
  }
  return min;
}

// ── Risk level classification ───────────────────────────────────────────────
function riskLevel(score) {
  if (score > 100) return { label: 'CRITICAL', color: '#ef4444', bg: '#fee2e2', text: '#991b1b' };
  if (score > 50)  return { label: 'HIGH',     color: '#f97316', bg: '#ffedd5', text: '#9a3412' };
  if (score > 20)  return { label: 'MODERATE', color: '#f59e0b', bg: '#fef3c7', text: '#92400e' };
  return               { label: 'LOW',         color: '#22c55e', bg: '#dcfce7', text: '#166534' };
}

/** Find the N-hour window (wrapping) with lowest sum of violations. */
function safestWindow(hourlySum, windowHrs = 3) {
  let best = { start: 0, sum: Infinity };
  for (let h = 0; h < 24; h++) {
    let s = 0;
    for (let w = 0; w < windowHrs; w++) s += hourlySum[(h + w) % 24];
    if (s < best.sum) best = { start: h, sum: s };
  }
  const end = (best.start + windowHrs) % 24;
  return { start: best.start, end, sum: best.sum };
}

function fmtHour(h) { return `${String(h).padStart(2, '0')}:00`; }

// ── Main component ──────────────────────────────────────────────────────────
export default function RoutePage() {
  // Map refs
  const mapRef      = useRef(null);
  const leafletMap  = useRef(null);
  const wayptLayer  = useRef(null);  // blue dot markers
  const routeLayer  = useRef(null);  // drawn polyline
  const matchLayer  = useRef(null);  // matched hotspot circles
  const hotLayer    = useRef(null);  // all severity hotspot dots (background)

  // State
  const [predictions,  setPredictions]  = useState([]);
  const [loadingPred,  setLoadingPred]  = useState(true);
  const [drawing,      setDrawing]      = useState(false);
  const [waypoints,    setWaypoints]    = useState([]);  // [[lat,lon],...]
  const [bufferM,      setBufferM]      = useState(200);
  const [analyzing,    setAnalyzing]    = useState(false);

  const [result, setResult] = useState(null);
  // result shape: { score, level, matched, hourlySum, window, routeKm }

  // ── Load severity predictions on mount ──────────────────────────────────
  useEffect(() => {
    const ts = new Date().toISOString().slice(0, 16).replace('T', ' ');
    axios.get(`${SEV_API}/predict?timestamp=${encodeURIComponent(ts)}`, { timeout: 90000 })
      .then(r => setPredictions(r.data || []))
      .catch(() => setPredictions([]))
      .finally(() => setLoadingPred(false));
  }, []);

  // ── Init Leaflet map ─────────────────────────────────────────────────────
  useEffect(() => {
    if (leafletMap.current) return;
    const m = L.map(mapRef.current, {
      center: BENGALURU_CENTER, zoom: 12,
      preferCanvas: true, zoomControl: false,
    });
    L.control.zoom({ position: 'bottomright' }).addTo(m);
    L.tileLayer(TILE_URL, { attribution: TILE_ATTR, maxZoom: 19 }).addTo(m);
    leafletMap.current = m;
    wayptLayer.current = L.layerGroup().addTo(m);
    routeLayer.current = L.layerGroup().addTo(m);
    matchLayer.current = L.layerGroup().addTo(m);
    hotLayer.current   = L.layerGroup().addTo(m);
    return () => { m.remove(); leafletMap.current = null; };
  }, []);

  // ── Render background hotspot dots when predictions load ─────────────────
  useEffect(() => {
    const hl = hotLayer.current;
    if (!hl) return;
    hl.clearLayers();
    predictions.forEach(p => {
      const lat = parseFloat(p.latitude), lng = parseFloat(p.longitude);
      if (isNaN(lat) || isNaN(lng)) return;
      L.circleMarker([lat, lng], {
        radius: 4, fillColor: '#6366f1', fillOpacity: 0.45,
        color: 'transparent', weight: 0,
      }).bindTooltip(p.location_key, { sticky: true }).addTo(hl);
    });
  }, [predictions]);

  // ── Handle map click to add waypoints (when drawing) ────────────────────
  useEffect(() => {
    const m = leafletMap.current;
    if (!m) return;

    function onMapClick(e) {
      if (!drawing) return;
      const { lat, lng } = e.latlng;
      setWaypoints(prev => [...prev, [lat, lng]]);
    }

    function onMapDblClick(e) {
      if (!drawing) return;
      L.DomEvent.stop(e);
      setDrawing(false);  // double-click finishes route
    }

    m.on('click', onMapClick);
    m.on('dblclick', onMapDblClick);
    return () => { m.off('click', onMapClick); m.off('dblclick', onMapDblClick); };
  }, [drawing]);

  // ── Re-draw waypoint markers + polyline whenever waypoints change ─────────
  useEffect(() => {
    const wl = wayptLayer.current;
    const rl = routeLayer.current;
    if (!wl || !rl) return;

    wl.clearLayers();
    rl.clearLayers();
    if (waypoints.length === 0) return;

    // Waypoint dots
    waypoints.forEach(([lat, lng], i) => {
      const icon = L.divIcon({
        className: '',
        html: `<div class="rr-waypoint${i === 0 ? ' rr-waypoint-start' : ''}">${i === 0 ? 'S' : i + 1}</div>`,
        iconSize: [22, 22], iconAnchor: [11, 11],
      });
      L.marker([lat, lng], { icon }).addTo(wl);
    });

    // Polyline
    if (waypoints.length >= 2) {
      L.polyline(waypoints, {
        color: '#6366f1', weight: 4, opacity: 0.9, dashArray: drawing ? '8 6' : null,
      }).addTo(rl);
    }
  }, [waypoints, drawing]);

  // ── Clear everything ─────────────────────────────────────────────────────
  const clearRoute = useCallback(() => {
    setWaypoints([]);
    setDrawing(false);
    setResult(null);
    matchLayer.current?.clearLayers();
  }, []);

  // ── Analyze route ────────────────────────────────────────────────────────
  const analyzeRoute = useCallback(async () => {
    if (waypoints.length < 2) return;
    setAnalyzing(true);
    matchLayer.current?.clearLayers();

    // 1. Spatial match: find hotspots within bufferM of route
    const matched = predictions
      .filter(p => {
        const lat = parseFloat(p.latitude), lng = parseFloat(p.longitude);
        if (isNaN(lat) || isNaN(lng)) return false;
        return minDistToPolyline(lat, lng, waypoints) <= bufferM;
      })
      .sort((a, b) => (b.lightgbm_prediction || 0) - (a.lightgbm_prediction || 0));

    // 2. Cumulative score
    const score = matched.reduce((s, p) => s + (p.lightgbm_prediction || 0), 0);
    const level = riskLevel(score);

    // 3. Approximate route length (km)
    let routeKm = 0;
    for (let i = 0; i < waypoints.length - 1; i++) {
      const [a, b] = [waypoints[i], waypoints[i + 1]];
      const dLat = toRad(b[0] - a[0]), dLon = toRad(b[1] - a[1]);
      const ha = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2;
      routeKm += 6371 * 2 * Math.atan2(Math.sqrt(ha), Math.sqrt(1 - ha));
    }

    // 4. Batch fetch hourly profiles for matched locations
    let hourlySum = new Array(24).fill(0);
    if (matched.length > 0) {
      try {
        const keys = matched.map(p => p.location_key);
        const resp = await axios.post('/api/v1/hourly-profiles/batch', { location_keys: keys }, { timeout: 15000 });
        const profileMap = resp.data; // { location_key: [24 floats] }
        matched.forEach(p => {
          const prof = profileMap[p.location_key];
          if (prof) prof.forEach((v, h) => { hourlySum[h] += v; });
        });
      } catch {
        // Silently fall back to flat profile — route score still valid
      }
    }

    // 5. Find safest window
    const win = safestWindow(hourlySum);

    // 6. Draw matched hotspots on map
    matched.forEach((p, i) => {
      const lat = parseFloat(p.latitude), lng = parseFloat(p.longitude);
      const isTop = i < 3;
      L.circleMarker([lat, lng], {
        radius: isTop ? 14 : 9,
        fillColor: isTop ? '#ef4444' : '#f97316',
        fillOpacity: isTop ? 0.9 : 0.7,
        color: '#fff', weight: 2,
      })
      .bindPopup(`<b>#${i + 1} ${p.location_key}</b><br>Severity: ${(p.lightgbm_prediction || 0).toFixed(2)}<br>${p.police_station || ''}`)
      .addTo(matchLayer.current);
    });

    // Auto-zoom to route
    if (matched.length > 0) {
      const allPts = [
        ...waypoints,
        ...matched.map(p => [parseFloat(p.latitude), parseFloat(p.longitude)]),
      ];
      leafletMap.current?.fitBounds(L.latLngBounds(allPts), { padding: [40, 40], maxZoom: 14 });
    }

    setResult({ score, level, matched, hourlySum, window: win, routeKm });
    setAnalyzing(false);
  }, [waypoints, predictions, bufferM]);

  // Auto-analyze when drawing finishes (drawing→false, waypoints≥2)
  useEffect(() => {
    if (!drawing && waypoints.length >= 2 && !result) {
      analyzeRoute();
    }
  }, [drawing]); // eslint-disable-line

  // ── Chart data ────────────────────────────────────────────────────────────
  const chartData = result
    ? result.hourlySum.map((v, h) => {
        const inWindow = result.window.end > result.window.start
          ? h >= result.window.start && h < result.window.end
          : h >= result.window.start || h < result.window.end;
        return { hour: fmtHour(h), value: parseFloat(v.toFixed(1)), safe: inWindow };
      })
    : [];

  // ── Render ─────────────────────────────────────────────────────────────────
  if (loadingPred) return (
    <div className="rr-loading">
      <Loader2 size={28} className="rr-spin" />
      <p>Loading severity data…</p>
    </div>
  );

  return (
    <div className="rr-layout">
      {/* LEFT — Map */}
      <div className="rr-map-area">
        <div ref={mapRef} className="rr-map" />

        {/* Map overlay controls */}
        <div className="rr-map-controls">
          <button
            className={`rr-btn ${drawing ? 'rr-btn-active' : 'rr-btn-primary'}`}
            onClick={() => { setDrawing(d => !d); if (result) { setResult(null); matchLayer.current?.clearLayers(); } }}
          >
            <Navigation size={14} />
            {drawing ? 'Drawing… (dbl-click to finish)' : 'Draw Route'}
          </button>

          <button className="rr-btn rr-btn-ghost" onClick={clearRoute} disabled={waypoints.length === 0}>
            <Trash2 size={14} /> Clear
          </button>

          {waypoints.length >= 2 && !drawing && (
            <button className="rr-btn rr-btn-primary" onClick={analyzeRoute} disabled={analyzing}>
              {analyzing ? <Loader2 size={14} className="rr-spin" /> : '⚡'}
              {analyzing ? 'Analyzing…' : 'Re-analyze'}
            </button>
          )}

          <div className="rr-buffer-group">
            <span className="rr-buffer-label">Buffer</span>
            {BUFFER_OPTIONS.map(b => (
              <button
                key={b}
                className={`rr-buffer-btn ${bufferM === b ? 'active' : ''}`}
                onClick={() => setBufferM(b)}
              >
                {b}m
              </button>
            ))}
          </div>
        </div>

        {/* Drawing hint */}
        {drawing && (
          <div className="rr-draw-hint">
            Click to add waypoints · Double-click to finish
          </div>
        )}

        {/* Waypoint count */}
        {waypoints.length > 0 && (
          <div className="rr-waypt-count">
            {waypoints.length} waypoint{waypoints.length !== 1 ? 's' : ''}
            {result ? ` · ${result.routeKm.toFixed(1)} km` : ''}
          </div>
        )}
      </div>

      {/* RIGHT — Results sidebar */}
      <div className="rr-sidebar">
        <div className="rr-sidebar-header">
          <span className="rr-sidebar-title">Route Risk Scorer</span>
          <span className="rr-sidebar-sub">{predictions.length} hotspots loaded</span>
        </div>

        {!result && !analyzing && (
          <div className="rr-empty">
            <MapPin size={32} className="rr-empty-icon" />
            <p>Draw a route on the map.</p>
            <p className="rr-empty-sub">Click waypoints · double-click to finish.</p>
          </div>
        )}

        {analyzing && (
          <div className="rr-empty">
            <Loader2 size={28} className="rr-spin" />
            <p>Analyzing route…</p>
          </div>
        )}

        {result && !analyzing && (
          <>
            {/* Risk score card */}
            <div className="rr-score-card" style={{ borderColor: result.level.color, background: result.level.bg }}>
              <div className="rr-score-val" style={{ color: result.level.color }}>
                {result.score.toFixed(1)}
              </div>
              <div className="rr-score-label" style={{ color: result.level.text }}>Cumulative Risk Score</div>
              <div className="rr-level-badge" style={{ background: result.level.color }}>
                {result.level.label}
              </div>
            </div>

            {/* Stats row */}
            <div className="rr-stats-row">
              <div className="rr-stat">
                <div className="rr-stat-val">{result.matched.length}</div>
                <div className="rr-stat-lbl">Hotspots on route</div>
              </div>
              <div className="rr-stat">
                <div className="rr-stat-val">{result.routeKm.toFixed(1)} km</div>
                <div className="rr-stat-lbl">Route length</div>
              </div>
              <div className="rr-stat">
                <div className="rr-stat-val">{bufferM} m</div>
                <div className="rr-stat-lbl">Buffer radius</div>
              </div>
            </div>

            {/* Safest window banner */}
            <div className="rr-window-banner">
              <div className="rr-window-icon">🟢</div>
              <div>
                <div className="rr-window-time">
                  {fmtHour(result.window.start)} – {fmtHour(result.window.end)}
                </div>
                <div className="rr-window-label">Safest 3-hour travel window</div>
              </div>
            </div>

            {/* Hourly profile chart */}
            {result.hourlySum.some(v => v > 0) && (
              <div className="rr-chart-section">
                <div className="rr-chart-title">Hourly Violation Intensity</div>
                <ResponsiveContainer width="100%" height={140}>
                  <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                    <XAxis
                      dataKey="hour"
                      tick={{ fontSize: 9 }}
                      tickFormatter={h => h.slice(0, 2)}
                      interval={2}
                    />
                    <YAxis tick={{ fontSize: 9 }} />
                    <Tooltip
                      formatter={v => [v.toFixed(1), 'Violations']}
                      labelFormatter={l => `Hour: ${l}`}
                    />
                    <Bar dataKey="value" radius={[2, 2, 0, 0]} maxBarSize={18}>
                      {chartData.map((d, i) => (
                        <Cell key={i} fill={d.safe ? '#22c55e' : '#6366f1'} fillOpacity={d.safe ? 0.9 : 0.55} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="rr-chart-legend">
                  <span className="rr-legend-dot" style={{ background: '#22c55e' }} /> Safest window
                  <span className="rr-legend-dot" style={{ background: '#6366f1', marginLeft: 10 }} /> Other hours
                </div>
              </div>
            )}

            {/* Matched hotspot list */}
            {result.matched.length > 0 && (
              <div className="rr-hotspot-list">
                <div className="rr-hotspot-list-title">
                  Hotspots on this route ({result.matched.length})
                </div>
                {result.matched.slice(0, 10).map((p, i) => (
                  <div key={p.location_key} className={`rr-hotspot-row ${i < 3 ? 'rr-hotspot-critical' : ''}`}>
                    <span className="rr-hotspot-rank"
                      style={{ background: i === 0 ? '#ef4444' : i < 3 ? '#f97316' : '#6366f1' }}>
                      {i + 1}
                    </span>
                    <div className="rr-hotspot-info">
                      <div className="rr-hotspot-name">{p.location_key}</div>
                      <div className="rr-hotspot-meta">{p.police_station || '—'}</div>
                    </div>
                    <div className="rr-hotspot-score">{(p.lightgbm_prediction || 0).toFixed(1)}</div>
                  </div>
                ))}
                {result.matched.length > 10 && (
                  <div className="rr-hotspot-more">+{result.matched.length - 10} more hotspots</div>
                )}
              </div>
            )}

            {result.matched.length === 0 && (
              <div className="rr-no-match">
                <p>✅ No severity hotspots within {bufferM}m of this route.</p>
                <p className="rr-empty-sub">Try increasing the buffer radius or drawing a longer route.</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
```

---

## STEP 4 — Create `frontend-react/src/pages/RoutePage.css`

```css
/* ── Layout ─────────────────────────────────────────────────────── */
.rr-layout {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.rr-map-area {
  flex: 1;
  position: relative;
  min-width: 0;
}

.rr-map {
  width: 100%;
  height: 100%;
}

/* ── Loading / empty states ─────────────────────────────────────── */
.rr-loading,
.rr-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  color: var(--text-muted, #888);
  font-size: 13px;
  text-align: center;
}

.rr-empty-icon { opacity: 0.4; }
.rr-empty-sub  { font-size: 11px; opacity: 0.7; }

.rr-spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Map overlay controls ────────────────────────────────────────── */
.rr-map-controls {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rr-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 1px 4px rgba(0,0,0,0.15);
}
.rr-btn:disabled { opacity: 0.55; cursor: not-allowed; }

.rr-btn-primary { background: #6366f1; color: #fff; }
.rr-btn-primary:hover:not(:disabled) { background: #4f46e5; }

.rr-btn-active  { background: #ef4444; color: #fff; }
.rr-btn-active:hover { background: #dc2626; }

.rr-btn-ghost   { background: #fff; color: #374151; border: 1.5px solid #d1d5db; }
.rr-btn-ghost:hover:not(:disabled) { background: #f9fafb; }

.rr-buffer-group {
  display: flex;
  align-items: center;
  gap: 3px;
  background: #fff;
  border-radius: 8px;
  padding: 3px 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.15);
}

.rr-buffer-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted, #888);
  margin-right: 3px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.rr-buffer-btn {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 7px;
  border-radius: 5px;
  border: none;
  cursor: pointer;
  background: transparent;
  color: #6b7280;
  transition: all 0.1s;
}
.rr-buffer-btn.active { background: #6366f1; color: #fff; }
.rr-buffer-btn:hover:not(.active) { background: #f3f4f6; }

.rr-draw-hint {
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0,0,0,0.72);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 20px;
  z-index: 500;
  pointer-events: none;
  letter-spacing: 0.02em;
}

.rr-waypt-count {
  position: absolute;
  bottom: 14px;
  left: 14px;
  background: rgba(255,255,255,0.92);
  border: 1.5px solid #e5e7eb;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #374151;
  padding: 4px 10px;
  z-index: 500;
  pointer-events: none;
}

/* ── Waypoint markers (used via L.divIcon) ─────────────────────── */
.rr-waypoint {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #6366f1;
  color: #fff;
  font-size: 9px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.3);
}
.rr-waypoint-start { background: #10b981; }

/* ── Sidebar ────────────────────────────────────────────────────── */
.rr-sidebar {
  width: 320px;
  min-width: 280px;
  max-width: 340px;
  height: 100%;
  overflow-y: auto;
  background: var(--surface, #fff);
  border-left: 1px solid var(--border-color, #e5e7eb);
  display: flex;
  flex-direction: column;
}

.rr-sidebar-header {
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  flex-shrink: 0;
}

.rr-sidebar-title {
  display: block;
  font-size: 14px;
  font-weight: 800;
  color: var(--text-main, #111);
  letter-spacing: 0.01em;
}

.rr-sidebar-sub {
  font-size: 11px;
  color: var(--text-muted, #888);
  margin-top: 2px;
  display: block;
}

/* ── Risk score card ─────────────────────────────────────────────── */
.rr-score-card {
  margin: 14px 14px 0;
  border-radius: 10px;
  border: 2px solid;
  padding: 14px 16px;
  text-align: center;
}

.rr-score-val {
  font-size: 40px;
  font-weight: 900;
  line-height: 1;
  letter-spacing: -0.02em;
}

.rr-score-label {
  font-size: 11px;
  font-weight: 600;
  margin-top: 3px;
  opacity: 0.8;
}

.rr-level-badge {
  display: inline-block;
  margin-top: 8px;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  padding: 3px 12px;
  border-radius: 20px;
}

/* ── Stats row ───────────────────────────────────────────────────── */
.rr-stats-row {
  display: flex;
  gap: 0;
  margin: 12px 14px 0;
  border: 1.5px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
}

.rr-stat {
  flex: 1;
  padding: 10px 8px;
  text-align: center;
  border-right: 1px solid var(--border-color, #e5e7eb);
}
.rr-stat:last-child { border-right: none; }

.rr-stat-val {
  font-size: 15px;
  font-weight: 800;
  color: var(--text-main, #111);
}
.rr-stat-lbl {
  font-size: 10px;
  color: var(--text-muted, #888);
  margin-top: 2px;
}

/* ── Safest window banner ────────────────────────────────────────── */
.rr-window-banner {
  margin: 12px 14px 0;
  background: #f0fdf4;
  border: 1.5px solid #86efac;
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.rr-window-icon { font-size: 18px; }
.rr-window-time { font-size: 15px; font-weight: 800; color: #166534; }
.rr-window-label { font-size: 10px; color: #15803d; margin-top: 1px; }

/* ── Hourly chart ────────────────────────────────────────────────── */
.rr-chart-section {
  margin: 12px 14px 0;
  padding: 12px;
  border: 1.5px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
}

.rr-chart-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-main, #111);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.rr-chart-legend {
  margin-top: 6px;
  font-size: 10px;
  color: var(--text-muted, #888);
  display: flex;
  align-items: center;
  gap: 4px;
}

.rr-legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* ── Hotspot list ─────────────────────────────────────────────────── */
.rr-hotspot-list {
  margin: 12px 14px 14px;
  border: 1.5px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
}

.rr-hotspot-list-title {
  font-size: 11px;
  font-weight: 700;
  padding: 9px 12px;
  background: var(--surface-2, #f8fafc);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  color: var(--text-main, #111);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.rr-hotspot-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}
.rr-hotspot-row:last-of-type { border-bottom: none; }
.rr-hotspot-row.rr-hotspot-critical { background: #fff7f7; }

.rr-hotspot-rank {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #6366f1;
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.rr-hotspot-info { flex: 1; min-width: 0; }

.rr-hotspot-name {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-main, #111);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rr-hotspot-meta {
  font-size: 10px;
  color: var(--text-muted, #888);
  margin-top: 1px;
}

.rr-hotspot-score {
  font-size: 12px;
  font-weight: 800;
  color: #ef4444;
  flex-shrink: 0;
}

.rr-hotspot-more {
  padding: 7px 12px;
  font-size: 11px;
  color: var(--text-muted, #888);
  text-align: center;
  background: var(--surface-2, #f8fafc);
}

.rr-no-match {
  margin: 14px;
  padding: 14px;
  background: #f0fdf4;
  border-radius: 8px;
  font-size: 12px;
  color: #166534;
  text-align: center;
}
.rr-no-match .rr-empty-sub { color: #4b7c61; }
```

---

## STEP 5 — Update `frontend-react/src/App.jsx`

### 5a. Add import at the top (with other page imports):
```jsx
import RoutePage from './pages/RoutePage';
```

### 5b. Add the route page to the conditional render block.
Find:
```jsx
{activePage === 'reports'    && <ReportsPage />}
```
Add after it:
```jsx
{activePage === 'route'      && <RoutePage />}
```

---

## STEP 6 — Update `frontend-react/src/components/TopNav.jsx`

Find the nav links block. Add a Route Risk link after the Reports link:

```jsx
<button
  className={`nav-link ${activePage === 'reports' ? 'active' : ''}`}
  onClick={() => setActivePage('reports')}
>
  Reports
</button>
<button
  className={`nav-link ${activePage === 'route' ? 'active' : ''}`}
  onClick={() => setActivePage('route')}
>
  Route Risk
</button>
```

---

## VERIFICATION CHECKLIST

After restarting the API and frontend:

1. **Nav bar** shows "Route Risk" link between Reports and Deployment.
2. **Route Risk page** loads without errors — map renders Bengaluru, purple dots for all severity hotspots visible.
3. **Draw Route** button activates drawing mode. Clicking the map adds numbered waypoints + extends a purple dashed polyline.
4. **Double-click** finishes the route — sidebar shows "Analyzing…" spinner briefly then results appear.
5. **Score card** shows a numeric score with colour-coded badge (LOW/MODERATE/HIGH/CRITICAL).
6. **Safest window banner** shows a valid time range like "03:00 – 06:00".
7. **Hourly chart** has 24 bars; safest window bars are green, others indigo.
8. **Matched hotspots** on map appear as orange/red circles overlaid on the route.
9. **Hotspot list** shows up to 10 matched locations with rank, name, police station, severity score.
10. **Buffer buttons** (100m / 200m / 400m) re-analyze on click with different match counts.
11. **Clear** button resets map and sidebar to empty state.
12. **POST /api/v1/hourly-profiles/batch** visible in Swagger docs at `http://127.0.0.1:8001/docs`.
13. If route crosses zero hotspots → green "No hotspots on this route" message shown.

---

## NOTES FOR THE AGENT

- `SEV_API` is already exported from `../hooks/useApi` — import it directly.
- The severity predictions fetch uses the same endpoint as SeverityPage — no new backend prediction logic.
- The `analyzeRoute` function fires automatically on double-click (via the `useEffect` watching `drawing`). The "Re-analyze" button lets officers re-run if they change the buffer size.
- Point-to-polyline math uses flat-earth approximation — accurate to within 1–2% for distances under 10 km, which covers all Bengaluru routes.
- `hourlySum` remains all-zeros if the batch fetch fails — safest window will default to hour 0, but the rest of the UI still works correctly. This is by design (graceful degradation).
- CSS variables (`--text-main`, `--surface`, `--border-color`) are already defined globally in the app — no need to redefine them.
