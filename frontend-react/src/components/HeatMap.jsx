import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { riskColor, sevRiskColor, scoreKey } from '../utils/colorUtils';
import { getSeverityNarrative } from '../utils/severityUtils';
import { highwayLabel } from '../utils/roadNameUtils';
import './HeatMap.css';

const BENGALURU_CENTER = [12.9716, 77.5946];


const HOTSPOT_COLORS = { 1: '#ef4444', 2: '#f59e0b', 3: '#f97316' };
// Voyager tiles: colorful, detailed, makes vibrant markers pop without going full-dark
const TILE_URL  = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

const GROQ_KEY   = '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';
const GROQ_URL   = 'https://api.groq.com/openai/v1/chat/completions';
const GROQ_MODEL = 'llama-3.3-70b-versatile';



const HeatMap = ({ predictions, selectedModel, colorScheme, displayTopN = 500, roadNames = {} }) => {
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
        buildPopup(loc, rank, selectedModel, score, logRatio, colorFn, colorScheme, roadNames),
        { maxWidth: 320 }
      );
      marker._locData = loc;
      marker._rank    = rank;

      // Permanent road name label for top-5 severity hotspots
      if (colorScheme === 'severity' && rank <= 5) {
        const locRoads = roadNames[loc.location_key];
        if (locRoads && locRoads.length > 0) {
          marker.bindTooltip(locRoads[0].name, {
            permanent: true,
            direction: 'top',
            offset: [0, rank <= 3 ? -14 : -10],
            className: `road-name-label${rank === 1 ? ' road-label-rank1' : ''}`,
          });
        }
      }

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

    const onPopupOpen = async (e) => {
      const src = e.popup._source;
      if (!src || !src._locData) return;
      const loc    = src._locData;
      const rank   = src._rank;
      const safeId = loc.location_key.replace(/[^a-z0-9]/gi, '_');
      const el     = document.getElementById(`ai-suggest-${safeId}`);
      if (!el || el.dataset.loaded === 'true') return;
      el.dataset.loaded = 'true';

      const VEH = { two_wheeler:'two-wheeler', auto_rickshaw:'auto-rickshaw', car:'car',
                    lcv:'light commercial vehicle', bus:'bus', heavy_truck:'heavy truck', tractor:'tractor' };
      const vehLabel  = VEH[loc.dominant_vehicle_cat] || (loc.dominant_vehicle_cat || 'mixed');
      const violation = loc.dominant_violation || 'parking violation';
      const zone      = loc.zone ? loc.zone.label : 'general area';
      const laneCount = loc.lane_count != null ? loc.lane_count.toFixed(1) : 'unknown';

      const prompt = `You are a traffic flow management expert for Bengaluru. Answer in EXACTLY 2 lines, NO extra text.

Data:
- Location: ${loc.area || 'Unknown'}, ${loc.police_station || ''} police station
- Violation: ${violation}
- Vehicle: ${vehLabel}
- Lanes: ${laneCount}
- Zone: ${zone}
- City rank: #${rank}

Rules:
- Each answer = max 9 words. Noun phrases only. Be specific to this exact location.
- REGION = why traffic congestion or violation peaks HERE (land use, road geometry, demand).
- CONTROL = a traffic MANAGEMENT action to reduce congestion/violation — e.g. deploy personnel, signal retiming, diversion route, barricades, lane channelisation, no-entry hours, dedicated bus bay. NOT enforcement like fines or wheel clamps.

Examples of CORRECT format:
REGION: Narrow 2-lane road serving high-density bus terminus
CONTROL: Deploy traffic personnel during morning peak hours

REGION: Commercial market with no service lane for loading
CONTROL: Enforce one-way flow with movable barricades

REGION: School zone, footpath parking blocks pedestrian movement
CONTROL: Stagger school timings, deploy marshal at entry gate

Now answer for the data above:
REGION: [max 9 words]
CONTROL: [max 9 words, traffic management — no fines/clamps]`;

      try {
        const res  = await fetch(GROQ_URL, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${GROQ_KEY}` },
          body:    JSON.stringify({ model: GROQ_MODEL, messages: [{ role: 'user', content: prompt }], max_tokens: 80, temperature: 0.3 }),
        });
        const data       = await res.json();
        const text       = data.choices?.[0]?.message?.content || '';
        const regionMatch  = text.match(/REGION:\s*(.+)/);
        const controlMatch = text.match(/CONTROL:\s*(.+)/);
        const region  = regionMatch  ? regionMatch[1].trim()  : 'No insight available.';
        const control = controlMatch ? controlMatch[1].trim() : 'No control action available.';

        el.className = 'popup-ai-suggest';
        el.innerHTML = `
          <div class="ai-unified-card">
            <div class="ai-card-header">
              <span class="ai-card-title">AI Insights</span>
              <span class="ai-card-powered">Groq AI</span>
            </div>
            <div class="ai-card-row">
              <div>
                <span class="ai-card-label">Why here</span>
                <p class="ai-card-text">${escH(region)}</p>
              </div>
            </div>
            <div class="ai-card-divider"></div>
            <div class="ai-card-row">
              <div>
                <span class="ai-card-label">Traffic Control</span>
                <p class="ai-card-text">${escH(control)}</p>
              </div>
            </div>
          </div>`;
      } catch {
        el.innerHTML = `<span class="ai-suggest-error">AI suggestions unavailable</span>`;
      }
    };

    m.on('popupopen', onPopupOpen);
    return () => m.off('popupopen', onPopupOpen);
  }, [predictions, selectedModel, colorScheme, roadNames]);

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

function buildPopup(loc, rank, model, score, logRatio, colorFn, colorScheme, roadNames = {}) {
  const safeId    = loc.location_key.replace(/[^a-z0-9]/gi, '_');
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
    const { headline, detail, blockagePct } = getSeverityNarrative(loc);

    const VEH = {
      two_wheeler:'two-wheelers', auto_rickshaw:'auto-rickshaws', car:'cars',
      lcv:'light commercial vehicles', bus:'buses', heavy_truck:'heavy trucks', tractor:'tractors',
    };
    const lane     = loc.lane_count != null ? loc.lane_count.toFixed(1) : '—';
    const vehLabel = VEH[loc.dominant_vehicle_cat] || (loc.dominant_vehicle_cat || '—');
    const vioType  = loc.dominant_violation || '—';

    const barColor = blockagePct >= 80 ? '#ef4444' : blockagePct >= 50 ? '#f59e0b' : '#22c55e';

    const locRoads = roadNames[loc.location_key] || [];
    const roadRowsHtml = locRoads.length > 0
      ? `<div class="popup-road-names">
           <div class="prn-label">Affected Roads</div>
           ${locRoads.map((r, i) => `
             <div class="prn-row${i === 0 ? ' prn-primary' : ''}">
               <span class="prn-dot"></span>
               <span class="prn-name">${escH(r.name)}</span>
               <span class="prn-hw">${highwayLabel(r.highway)}</span>
             </div>`).join('')}
         </div>`
      : '';

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
      ${roadRowsHtml}
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
      <div id="ai-suggest-${safeId}" class="popup-ai-suggest popup-ai-loading">
        <span class="ai-loading-dot"></span> Getting AI insights…
      </div>
    </div>`;
}

export default HeatMap;
