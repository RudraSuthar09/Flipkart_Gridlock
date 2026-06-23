import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { riskColor, sevRiskColor, scoreKey } from '../utils/colorUtils';
import './HeatMap.css';

const BENGALURU_CENTER = [12.9716, 77.5946];
const HOTSPOT_COLORS = { 1: '#ef4444', 2: '#f59e0b', 3: '#f97316' };
// Voyager tiles: colorful, detailed, makes vibrant markers pop without going full-dark
const TILE_URL  = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';



const HeatMap = ({ predictions, selectedModel, colorScheme, displayTopN = 500 }) => {
  const mapRef         = useRef(null);
  const leafletMap     = useRef(null);
  const markerLayer    = useRef(null);
  const canvasRenderer = useRef(null);

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

    const sorted = [...predictions].sort((a, b) => (b[key] || 0) - (a[key] || 0));
    const n      = sorted.length;

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

      // Blend log-score (data-driven) + rank-position (spread enforcer)
      const logRatio  = logMax > 0 ? Math.log1p(score) / logMax : 0;
      const rankRatio = n > 1 ? 1 - (idx / (n - 1)) : 1;
      const ratio = Math.min(1, 0.7 * logRatio + 0.3 * rankRatio);

      // Always score-based color — zone info shown via outline only, not fill override
      const color   = colorFn(ratio);
      const isTop20 = rank <= 20;
      const isTop5  = rank <= 5;

      // Base radius in pixels — sized to be clearly visible at any zoom level.
      let baseRadius = 6;
      if (isTop5)           baseRadius = 16;
      else if (isTop20)     baseRadius = 12;
      else if (rank <= 100) baseRadius = 9;
      else if (ratio > 0.4) baseRadius = 7;

      // Narrow-lane bonus for severity view
      if (colorScheme === 'severity' && loc.lane_count != null) {
        baseRadius += Math.max(0, (2 - loc.lane_count) * 2);
      }

      // Border: white for top-20, zone-colour outline for zone locations, none otherwise
      const outlineColor = isTop20 ? '#ffffff'
        : loc.zone ? loc.zone.color
        : 'transparent';
      const outlineWeight = (isTop20 || loc.zone) ? 1.5 : 0;

      let marker;
      if (rank <= 3) {
        const hColor = HOTSPOT_COLORS[rank];
        const icon = L.divIcon({
          className: '',
          html: `<div class="hotspot-pulse" style="background:${hColor};"></div>`,
          iconSize: [18, 18],
          iconAnchor: [9, 9],
          popupAnchor: [0, -10],
        });
        marker = L.marker([lat, lng], { icon, bubblingMouseEvents: false });
      } else {
        marker = L.circleMarker([lat, lng], {
          renderer:    canvasRenderer.current,
          radius:      baseRadius,
          fillColor:   color,
          fillOpacity: isTop5 ? 0.95 : isTop20 ? 0.85 : (rank <= 100 ? 0.75 : 0.65),
          color:       outlineColor,
          weight:      outlineWeight,
          bubblingMouseEvents: false,
        });
      }

      marker.bindPopup(
        buildPopup(loc, rank, selectedModel, score, logRatio, colorFn, colorScheme),
        { maxWidth: 320 }
      );
      layer.addLayer(marker);
    });

    layer.addTo(m);
    markerLayer.current = layer;

    // Auto-zoom when predictions are a filtered subset (station filter active)
    if (sorted.length > 0 && sorted.length < 500) {
      const validLatLngs = sorted
        .slice(0, Math.min(sorted.length, 100))
        .map(p => [parseFloat(p.latitude), parseFloat(p.longitude)])
        .filter(([lat, lng]) => !isNaN(lat) && !isNaN(lng));
      if (validLatLngs.length > 1) {
        m.fitBounds(L.latLngBounds(validLatLngs), { padding: [40, 40], maxZoom: 14 });
      }
    }
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

  const isTop3 = rank <= 3;
  const badge = isTop3
    ? `<span class="popup-rank-badge popup-rank-top">🔴 #${rank} PRIORITY ${isSev ? 'SEVERITY ' : ''}HOTSPOT</span>`
    : isTop5
    ? `<span class="popup-rank-badge popup-rank-top">#${rank} ${isSev ? 'SEVERITY ' : ''}HOTSPOT</span>`
    : `<span class="popup-rank-badge">#${rank}</span>`;

  const mapsLink = isTop3
    ? `<a class="popup-maps-link" href="https://maps.google.com/?q=${loc.latitude},${loc.longitude}" target="_blank" rel="noreferrer">Open in Maps →</a>`
    : '';

  const zoneBadge = loc.zone ? `
    <div class="popup-zone-badge" style="background:${loc.zone.color}15;border:1px solid ${loc.zone.color};color:${loc.zone.color}">
      <span class="popup-zone-tag" style="background:${loc.zone.color};color:#fff">${escH(loc.zone.short)}</span>
      <div class="popup-zone-info">
        <span class="popup-zone-label">${escH(loc.zone.label)}</span>
        <span class="popup-zone-poi">${escH(loc.zone.poi.name)} &middot; ${loc.zone.distanceM}m</span>
      </div>
    </div>` : '';

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
        <span class="sev-explainer-icon">⚠</span>
        <em>Mostly ${escH(vehLabel)} violations on ${escH(roadDesc)} road — real traffic impact</em>
      </div>
      <div class="sev-details-grid">
        <div class="sev-detail-item"><span class="sev-detail-label">Lane count</span><span class="sev-detail-val">${escH(lane)}</span></div>
        <div class="sev-detail-item"><span class="sev-detail-label">Vehicle type</span><span class="sev-detail-val">${escH(vehLabel)}</span></div>
        <div class="sev-detail-item sev-detail-wide"><span class="sev-detail-label">Common violation</span><span class="sev-detail-val">${escH(vioType)}</span></div>
      </div>`;
  } else {
    sevFields = `
      <div class="count-explainer">
        <span>📍</span>
        <em>Predicted illegal parking events at this location</em>
      </div>`;
  }

  let roadRow = '';
  if (loc.road_label) {
    const onewayBadge = loc.is_oneway
      ? `<span class="popup-oneway-badge">ONE-WAY</span>` : '';
    const roadName = loc.osm_road_name ? ` &mdash; ${escH(loc.osm_road_name)}` : '';
    roadRow = `
      <div class="popup-road-row">
        <span class="popup-road-label">${escH(loc.road_label)}${roadName}</span>
        ${onewayBadge}
      </div>`;
  }

  return `
    <div class="pred-popup ${isSev ? 'sev-popup' : ''}">
      <div class="popup-badges">${badge}${zoneBadge}</div>
      <div class="popup-loc">${escH(loc.location_key)}</div>
      <div class="popup-meta">
        <span>${escH(loc.area || '—')}</span>
        <span>${escH(loc.police_station || '—')}</span>
      </div>
      ${roadRow}
      ${sevFields}
      <div class="popup-scores">
        <div class="popup-score ${model === 'lightgbm' ? 'active-score' : ''}">
          <span class="score-label">AI Score</span>
          <span class="score-val">${(loc.lightgbm_prediction || 0).toFixed(2)}</span>
        </div>
        <div class="popup-score ${model === 'baseline' ? 'active-score' : ''}">
          <span class="score-label">Baseline</span>
          <span class="score-val">${(loc.baseline_prediction || 0).toFixed(2)}</span>
        </div>
        <div class="popup-score ${model === 'naive' ? 'active-score' : ''}">
          <span class="score-label">Naive</span>
          <span class="score-val">${(loc.naive_prediction || 0).toFixed(1)}</span>
        </div>
      </div>
      <div class="popup-risk-bar">
        <div class="popup-risk-fill" style="width:${visualPct}%;background:${color}"></div>
      </div>
      <div class="popup-risk-label">${isSev ? 'Severity' : 'Risk'}: ${visualPct}% · Score: ${score.toFixed(2)} · Rank #${rank}</div>
      ${mapsLink}
    </div>`;
}

export default HeatMap;
