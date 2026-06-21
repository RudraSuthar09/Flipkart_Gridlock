import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { riskColor, sevRiskColor, scoreKey } from '../utils/colorUtils';
import './HeatMap.css';

const BENGALURU_CENTER = [12.9716, 77.5946];
const TILE_URL  = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

const HeatMap = ({ predictions, selectedModel, colorScheme, displayTopN = 500 }) => {
  const mapRef        = useRef(null);
  const leafletMap    = useRef(null);
  const markerLayer   = useRef(null);
  const canvasRenderer= useRef(null);

  // ── Init map once ────────────────────────────────────
  useEffect(() => {
    if (leafletMap.current) return;
    canvasRenderer.current = L.canvas({ padding: 0.5 });

    const m = L.map(mapRef.current, {
      center: BENGALURU_CENTER,
      zoom: 11,
      preferCanvas: true,
      zoomControl: false,
    });
    L.control.zoom({ position: 'bottomright' }).addTo(m);
    L.tileLayer(TILE_URL, { attribution: TILE_ATTR, maxZoom: 19 }).addTo(m);
    leafletMap.current = m;

    return () => { m.remove(); leafletMap.current = null; };
  }, []);

  // ── Invalidate size (fixes blank-map on first render) ─
  useEffect(() => {
    const t = setTimeout(() => {
      if (leafletMap.current) leafletMap.current.invalidateSize();
    }, 80);
    return () => clearTimeout(t);
  });

  // ── Re-render ALL markers when data / model change ────
  useEffect(() => {
    const m = leafletMap.current;
    if (!m) return;

    if (markerLayer.current) { m.removeLayer(markerLayer.current); markerLayer.current = null; }
    if (!predictions || predictions.length === 0) return;

    const key    = scoreKey(selectedModel);
    const colorFn = colorScheme === 'severity' ? sevRiskColor : riskColor;

    // Sort descending — backend already filters to active locations only
    const sorted = [...predictions].sort((a, b) => (b[key] || 0) - (a[key] || 0));
    const n      = sorted.length;

    // Compute log of all scores for normalization
    const logScores = sorted.map(p => Math.log1p(p[key] || 0));
    const logMax    = Math.max(...logScores, 1e-9);

    const rankMap = new Map(sorted.map((p, i) => [p.location_key, i + 1]));

    const layer = L.layerGroup();

    sorted.slice(0, displayTopN).forEach((loc, idx) => {
      const lat = parseFloat(loc.latitude);
      const lng = parseFloat(loc.longitude);
      if (isNaN(lat) || isNaN(lng)) return;

      const score = loc[key] || 0;
      const rank  = rankMap.get(loc.location_key);

      // ── Normalized visual ratio ─────────────────────────
      // Heavy-tailed distribution: blend log-score + rank-position
      // so all locations get meaningful, spread-out colors.
      const logRatio  = logMax > 0 ? Math.log1p(score) / logMax : 0;
      const rankRatio = n > 1 ? 1 - (idx / (n - 1)) : 1;
      // 70% log-score (data-driven) + 30% rank (spread enforcer)
      const ratio = Math.min(1, 0.7 * logRatio + 0.3 * rankRatio);

      const color   = colorFn(ratio);
      const isTop20 = rank <= 20;

      // ── Radius: top-ranked = bigger ─────────────────────
      let radius = 5; // default for all 6333 locations
      if (isTop20) radius = 10;
      else if (rank <= 100) radius = 7;
      else if (ratio > 0.4) radius = 6;

      // Severity: narrow-lane bonus
      if (colorScheme === 'severity' && loc.lane_count != null) {
        const laneBonus = Math.max(0, (2 - loc.lane_count) * 1.5);
        radius = Math.min(radius + laneBonus, 14);
      }

      const marker = L.circleMarker([lat, lng], {
        renderer:    canvasRenderer.current,
        radius,
        fillColor:   color,
        fillOpacity: isTop20 ? 1 : (rank <= 100 ? 0.85 : 0.7),
        color:       isTop20 ? '#ffffff' : 'transparent',
        weight:      isTop20 ? 1.5 : 0,
        bubblingMouseEvents: false,
      });

      marker.bindPopup(
        buildPopup(loc, rank, selectedModel, score, logRatio, colorFn, colorScheme),
        { maxWidth: 320 }
      );
      layer.addLayer(marker);
    });

    layer.addTo(m);
    markerLayer.current = layer;
  }, [predictions, selectedModel, colorScheme]);

  return (
    <div className="heatmap-wrapper">
      <div ref={mapRef} className="heatmap-leaflet" />
    </div>
  );
};

// ── Popup builder ─────────────────────────────────────────
function escH(v) {
  return String(v ?? '—').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function buildPopup(loc, rank, model, score, logRatio, colorFn, colorScheme) {
  const visualPct = (logRatio * 100).toFixed(1);
  const isTop5 = rank <= 5;
  const isSev  = colorScheme === 'severity';
  const color  = colorFn(logRatio);

  const badge = isTop5
    ? `<span class="popup-rank-badge popup-rank-top">#${rank} ${isSev ? 'SEVERITY ' : ''}HOTSPOT</span>`
    : `<span class="popup-rank-badge">#${rank}</span>`;

  let sevFields = '';
  if (isSev) {
    const VEH = { two_wheeler:'two-wheeler', auto_rickshaw:'auto-rickshaw', car:'car',
                  lcv:'light commercial vehicle', bus:'bus', heavy_truck:'heavy truck', tractor:'tractor' };
    const lane     = loc.lane_count != null ? loc.lane_count.toFixed(1) : '—';
    const vehLabel = VEH[loc.dominant_vehicle_cat] || (loc.dominant_vehicle_cat || '—');
    const vioType  = loc.dominant_violation || '—';
    const laneNum  = loc.lane_count != null ? Math.round(loc.lane_count) : null;
    const roadDesc = laneNum != null ? (laneNum <= 1 ? 'single-lane' : `${laneNum}-lane`) : '';

    sevFields = `
      <div class="sev-explainer">
        <span class="sev-explainer-icon">ℹ</span>
        <em>Mostly ${escH(vehLabel)} violations on ${escH(roadDesc)} road</em>
      </div>
      <div class="sev-details-grid">
        <div class="sev-detail-item"><span class="sev-detail-label">Lane count</span><span class="sev-detail-val">${escH(lane)}</span></div>
        <div class="sev-detail-item"><span class="sev-detail-label">Vehicle type</span><span class="sev-detail-val">${escH(vehLabel)}</span></div>
        <div class="sev-detail-item sev-detail-wide"><span class="sev-detail-label">Common violation</span><span class="sev-detail-val">${escH(vioType)}</span></div>
      </div>`;
  }

  return `
    <div class="pred-popup ${isSev ? 'sev-popup' : ''}">
      ${badge}
      <div class="popup-loc">${escH(loc.location_key)}</div>
      <div class="popup-meta">
        <span>${escH(loc.area || '—')}</span>
        <span>${escH(loc.police_station || '—')}</span>
      </div>
      ${sevFields}
      <div class="popup-scores">
        <div class="popup-score ${model === 'lightgbm' ? 'active-score' : ''}">
          <span class="score-label">Risk Score (AI)</span>
          <span class="score-val">${(loc.lightgbm_prediction || 0).toFixed(2)}</span>
        </div>
        <div class="popup-score ${model === 'baseline' ? 'active-score' : ''}">
          <span class="score-label">Baseline (avg)</span>
          <span class="score-val">${(loc.baseline_prediction || 0).toFixed(2)}</span>
        </div>
        <div class="popup-score ${model === 'naive' ? 'active-score' : ''}">
          <span class="score-label">Naive (yesterday)</span>
          <span class="score-val">${(loc.naive_prediction || 0).toFixed(1)}</span>
        </div>
      </div>
      <div class="popup-risk-bar">
        <div class="popup-risk-fill" style="width:${visualPct}%;background:${color}"></div>
      </div>
      <div class="popup-risk-label">Risk: ${visualPct}% intensity · Score: ${score.toFixed(2)} · Rank #${rank}</div>
    </div>`;
}

export default HeatMap;
