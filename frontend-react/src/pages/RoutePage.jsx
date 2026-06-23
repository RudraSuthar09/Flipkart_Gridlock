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

// Module-level prediction cache — 2.8 MB payload, avoid re-fetching on navigation
let _predCache = null;

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
  const wayptLayer  = useRef(null);
  const routeLayer  = useRef(null);
  const matchLayer  = useRef(null);
  const hotLayer    = useRef(null);

  // State
  const [predictions,  setPredictions]  = useState(_predCache || []);
  const [loadingPred,  setLoadingPred]  = useState(!_predCache);
  const [drawing,      setDrawing]      = useState(false);
  const [waypoints,    setWaypoints]    = useState([]);
  const [bufferM,      setBufferM]      = useState(200);
  const [analyzing,    setAnalyzing]    = useState(false);

  const [result, setResult] = useState(null);

  // ── Load severity predictions on mount ──────────────────────────────────
  useEffect(() => {
    if (_predCache) return; // already loaded — instant navigation
    // Fetch health + a known good timestamp in parallel to cut latency
    Promise.all([
      axios.get(`${SEV_API}/health`, { timeout: 10000 }),
    ]).then(([h]) => {
      const ts = (h.data.panel_last_updated || '').slice(0, 16);
      return axios.get(`${SEV_API}/predict?timestamp=${encodeURIComponent(ts)}&active_only=false`, { timeout: 90000 });
    })
      .then(r => { _predCache = r.data || []; setPredictions(_predCache); })
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
    // Force Leaflet to recalculate tile bounds after the flex layout settles
    setTimeout(() => m.invalidateSize(), 100);
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
      setDrawing(false);
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

    waypoints.forEach(([lat, lng], i) => {
      const icon = L.divIcon({
        className: '',
        html: `<div class="rr-waypoint${i === 0 ? ' rr-waypoint-start' : ''}">${i === 0 ? 'S' : i + 1}</div>`,
        iconSize: [22, 22], iconAnchor: [11, 11],
      });
      L.marker([lat, lng], { icon }).addTo(wl);
    });

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

    // 1. Spatial match
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

    // 3. Route length (km) via haversine
    let routeKm = 0;
    for (let i = 0; i < waypoints.length - 1; i++) {
      const [a, b] = [waypoints[i], waypoints[i + 1]];
      const dLat = toRad(b[0] - a[0]), dLon = toRad(b[1] - a[1]);
      const ha = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2;
      routeKm += 6371 * 2 * Math.atan2(Math.sqrt(ha), Math.sqrt(1 - ha));
    }

    // 4. Batch fetch hourly profiles
    let hourlySum = new Array(24).fill(0);
    if (matched.length > 0) {
      try {
        const keys = matched.map(p => p.location_key);
        const resp = await axios.post('/api/v1/hourly-profiles/batch', { location_keys: keys }, { timeout: 15000 });
        const profileMap = resp.data;
        matched.forEach(p => {
          const prof = profileMap[p.location_key];
          if (prof) prof.forEach((v, h) => { hourlySum[h] += v; });
        });
      } catch {
        // Graceful degradation — score still valid
      }
    }

    // 5. Safest window
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

  // Auto-analyze when drawing finishes
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
  return (
    <div className="rr-layout">
      {/* LEFT — Map */}
      <div className="rr-map-area">
        <div ref={mapRef} className="rr-map" />

        {/* Loading overlay — keeps mapRef in DOM so Leaflet can init */}
        {loadingPred && (
          <div className="rr-map-loading-overlay">
            <Loader2 size={28} className="rr-spin" />
            <p>Loading severity data…</p>
          </div>
        )}

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

        {drawing && (
          <div className="rr-draw-hint">
            Click to add waypoints · Double-click to finish
          </div>
        )}

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

        {loadingPred && (
          <div className="rr-empty">
            <Loader2 size={22} className="rr-spin" />
            <p>Loading hotspots…</p>
          </div>
        )}

        {!loadingPred && !result && !analyzing && (
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
                <p>No severity hotspots within {bufferM}m of this route.</p>
                <p className="rr-empty-sub">Try increasing the buffer radius or drawing a longer route.</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
