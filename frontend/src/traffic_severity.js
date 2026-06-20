/* ═══════════════════════════════════════════════════════════════════
   traffic_severity.js — Severity-Weighted Heatmap page
   Route: #/traffic-severity
   API:   http://127.0.0.1:8001/api/v1/traffic-severity

   Key difference from only_prediction.js:
     • Color scale driven by SEVERITY (continuous Tweedie float), not count.
     • Marker radius scales with lane_count — narrow-road hotspots are larger.
     • Popup shows explainability: dominant vehicle type + violation + lane count.
     • Data-confidence banner reads /health coverage numbers.
     • Compare link → #/only-prediction for side-by-side view.
═══════════════════════════════════════════════════════════════════ */

const SEV_API = 'http://127.0.0.1:8001/api/v1/traffic-severity';
const SEV_CENTER = [12.9716, 77.5946];

// Always render the top N locations regardless of score magnitude.
// This prevents the heavy-tailed Tweedie distribution from hiding all
// markers when a single dominant hotspot inflates the relative threshold.
const SEV_TOP_N_ALWAYS_SHOW = 100;

/* ── State ─────────────────────────────────────────────────────── */
const sevState = {
  predictions:   [],
  selectedModel: 'lightgbm',
  healthData:    null,
  sevMap:        null,
  markerLayer:   null,
  renderer:      null,
  initialized:   false,
  loading:       false,
};

/* ── Color helpers (amber/orange theme — distinct from indigo count theme) ── */
function sevHexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function sevLerpColor(hex1, hex2, t) {
  const [r1, g1, b1] = sevHexToRgb(hex1);
  const [r2, g2, b2] = sevHexToRgb(hex2);
  return `rgb(${Math.round(r1+(r2-r1)*t)},${Math.round(g1+(g2-g1)*t)},${Math.round(b1+(b2-b1)*t)})`;
}

/**
 * Severity color scale: green → amber → deep orange → crimson.
 * Deliberately shifted more orange vs the count heatmap's green→red —
 * visual distinction makes it clear these are different metrics.
 *   0.0 → #10b981 (emerald)
 *   0.4 → #f59e0b (amber)
 *   0.7 → #ea580c (deep orange)
 *   1.0 → #dc2626 (crimson)
 */
function sevRiskColor(ratio) {
  if (ratio <= 0)   return '#10b981';
  if (ratio >= 1)   return '#dc2626';
  if (ratio < 0.4)  return sevLerpColor('#10b981', '#f59e0b', ratio / 0.4);
  if (ratio < 0.7)  return sevLerpColor('#f59e0b', '#ea580c', (ratio - 0.4) / 0.3);
  return sevLerpColor('#ea580c', '#dc2626', (ratio - 0.7) / 0.3);
}

/* ── Datetime helpers ───────────────────────────────────────────── */
function sevToDatetimeLocalValue(d) {
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

function sevDefaultDatetime() {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  return now;
}

/* ── API status indicator ───────────────────────────────────────── */
function setSevApiStatus(state, msg) {
  const dot  = document.getElementById('sev-api-dot');
  const text = document.getElementById('sev-api-text');
  if (!dot || !text) return;
  dot.className   = `api-dot api-dot-${state}`;
  text.textContent = msg;
}

/* ── Data-confidence banner ─────────────────────────────────────── */
function updateConfidenceBanner(health) {
  const banner = document.getElementById('sev-confidence-banner');
  if (!banner) return;

  if (!health) {
    banner.style.display = 'none';
    return;
  }

  const vCov = Math.round((health.vehicle_mapping_coverage || 0) * 100);
  const lCov = Math.round((health.lane_match_coverage      || 0) * 100);
  const allGood = vCov >= 95 && lCov >= 95;

  banner.style.display = 'flex';
  banner.className     = `sev-confidence-banner ${allGood ? 'banner-ok' : 'banner-warn'}`;
  banner.innerHTML     = `
    <span class="banner-icon">${allGood ? '✓' : '⚠'}</span>
    <span>Vehicle type known for <strong>${vCov}%</strong> of violations · 
          Lane data matched for <strong>${lCov}%</strong> of locations</span>`;
}

/* ── Health check ───────────────────────────────────────────────── */
async function checkSevApiHealth() {
  setSevApiStatus('loading', 'Connecting to severity API…');
  try {
    const res  = await fetch(`${SEV_API}/health`, { signal: AbortSignal.timeout(6000) });
    const data = await res.json();
    sevState.healthData = data;
    updateConfidenceBanner(data);

    if (data.status === 'ok' && data.model_loaded) {
      setSevApiStatus('ok', `API ready · ${(data.location_count || 0).toLocaleString()} locations`);

      // ── Set the default datetime to the last timestamp in the panel.
      // The dataset ends in 2024; defaulting to "now" (2026) gives zero lookback
      // features, so every location scores near-zero and nothing renders on the map.
      if (data.panel_last_updated) {
        const dtInput = document.getElementById('sev-datetime');
        if (dtInput) {
          // panel_last_updated is like "2024-04-08 17:00:00" — convert to datetime-local
          const panelEnd = new Date(data.panel_last_updated.replace(' ', 'T'));
          panelEnd.setMinutes(0, 0, 0);
          dtInput.value = sevToDatetimeLocalValue(panelEnd);
        }
      }
    } else {
      setSevApiStatus('error', 'Severity model not loaded — train first');
    }
  } catch {
    setSevApiStatus('error', 'Cannot reach API (port 8001)');
    updateConfidenceBanner(null);
  }
}

/* ── Loading overlay ────────────────────────────────────────────── */
function setSevLoading(on, msg) {
  const overlay = document.getElementById('sev-loading');
  const text    = document.getElementById('sev-loading-text');
  if (!overlay) return;
  overlay.style.display = on ? 'flex' : 'none';
  if (text && msg) text.textContent = msg;
  sevState.loading = on;
}

/* ── Run prediction ─────────────────────────────────────────────── */
async function runSevPrediction() {
  if (sevState.loading) return;
  const dtInput = document.getElementById('sev-datetime');
  if (!dtInput || !dtInput.value) {
    alert('Please pick a target date & hour first.');
    return;
  }

  const ts = dtInput.value;
  setSevLoading(true, 'Fetching severity predictions…');
  setSevApiStatus('loading', 'Predicting…');

  try {
    const url = `${SEV_API}/predict?timestamp=${encodeURIComponent(ts)}`;
    const res  = await fetch(url, { signal: AbortSignal.timeout(60000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    sevState.predictions = await res.json();

    setSevApiStatus('ok', `Done · ${sevState.predictions.length.toLocaleString()} locations`);
    updateSevMapMarkers();
    updateSevTop5();
    updateSevStats();
  } catch (err) {
    setSevApiStatus('error', 'Prediction failed: ' + err.message);
    console.error(err);
  } finally {
    setSevLoading(false);
  }
}

/* ── Map markers ────────────────────────────────────────────────── */
function sevScoreKey(model) { return `${model}_prediction`; }

function updateSevMapMarkers() {
  if (!sevState.sevMap) return;
  const preds = sevState.predictions;
  const model = sevState.selectedModel;
  const key   = sevScoreKey(model);

  const rawMaxScore = Math.max(...preds.map(p => p[key] || 0));
  const effectiveMax = Math.max(rawMaxScore, 1e-6);

  // Sort all predictions by score (descending) and take the top N to display.
  // Rank-based filtering is robust against heavy-tailed distributions where
  // a single dominant hotspot would inflate any percentage threshold.
  const sorted  = [...preds].sort((a, b) => (b[key] || 0) - (a[key] || 0));
  const rankMap = new Map(sorted.map((p, i) => [p.location_key, i + 1]));
  const visible = sorted.slice(0, SEV_TOP_N_ALWAYS_SHOW);

  if (sevState.markerLayer) {
    sevState.sevMap.removeLayer(sevState.markerLayer);
  }
  sevState.markerLayer = L.layerGroup();

  visible.forEach(loc => {
    const score    = loc[key] || 0;
    const ratio    = effectiveMax > 0 ? score / effectiveMax : 0;
    const rank     = rankMap.get(loc.location_key);
    const isTop20  = rank <= 20;
    const color    = sevRiskColor(ratio);

    // Narrow-lane locations get a slightly larger radius (§9 spec)
    // lane_count: 1 → biggest, 4+ → normal
    const laneCount = loc.lane_count || 2;
    const laneBonus = Math.max(0, (2 - laneCount) * 1.5);  // +1.5 per missing lane
    const baseRadius = isTop20 ? 9 : (ratio > 0.3 ? 6 : 5);
    const radius = Math.min(baseRadius + laneBonus, 14);

    const marker = L.circleMarker(
      [loc.latitude, loc.longitude],
      {
        renderer:    sevState.renderer,
        radius:      radius,
        fillColor:   color,
        fillOpacity: isTop20 ? 1 : 0.82,
        color:       isTop20 ? '#ffffff' : color,
        weight:      isTop20 ? 2 : 0,
        bubblingMouseEvents: false,
      }
    );

    marker.bindPopup(buildSevPopup(loc, rank, model, score, effectiveMax), { maxWidth: 300 });
    sevState.markerLayer.addLayer(marker);
  });

  sevState.markerLayer.addTo(sevState.sevMap);

  const dispEl = document.getElementById('sev-stat-disp');
  if (dispEl) dispEl.textContent = visible.length.toLocaleString();
}

/* ── Popup ──────────────────────────────────────────────────────── */
function sevEsc(v) {
  return String(v ?? '—')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function buildSevPopup(loc, rank, model, score, effectiveMax) {
  const pct    = effectiveMax > 0 ? ((score / effectiveMax) * 100).toFixed(1) : '0.0';
  const isTop5 = rank <= 5;
  const badge  = isTop5
    ? `<span class="popup-rank-badge popup-rank-top">#${rank} SEVERITY HOTSPOT</span>`
    : `<span class="popup-rank-badge sev-rank-badge">#${rank}</span>`;

  const lane    = loc.lane_count != null ? loc.lane_count.toFixed(1) : '—';
  const vehCat  = loc.dominant_vehicle_cat || '—';
  const vioType = loc.dominant_violation   || '—';

  // Plain-language explainability summary (the spec's "differentiator")
  const vehLabel = {
    two_wheeler:  'two-wheeler',
    auto_rickshaw:'auto-rickshaw',
    car:          'car',
    lcv:          'light commercial vehicle',
    bus:          'bus',
    heavy_truck:  'heavy truck',
    tractor:      'tractor',
  }[vehCat] || vehCat;

  const laneNum = loc.lane_count != null ? Math.round(loc.lane_count) : null;
  const roadDesc = laneNum != null
    ? (laneNum <= 1 ? 'a single-lane road' : `a ${laneNum}-lane road`)
    : 'road';

  const explainer = `Mostly ${vehLabel} violations on ${roadDesc}`;

  const color = sevRiskColor(score / (effectiveMax || 1));


  return `
    <div class="pred-popup sev-popup">
      ${badge}
      <div class="popup-loc">${sevEsc(loc.location_key)}</div>
      <div class="popup-meta">
        <span>${sevEsc(loc.area || '—')}</span>
        <span>${sevEsc(loc.police_station || '—')}</span>
      </div>

      <!-- Explainability (the key Part 2 differentiator) -->
      <div class="sev-explainer">
        <span class="sev-explainer-icon">ℹ</span>
        <em>${sevEsc(explainer)}</em>
      </div>

      <div class="sev-details-grid">
        <div class="sev-detail-item">
          <span class="sev-detail-label">Lane count</span>
          <span class="sev-detail-val">${lane}</span>
        </div>
        <div class="sev-detail-item">
          <span class="sev-detail-label">Vehicle type</span>
          <span class="sev-detail-val">${sevEsc(vehLabel)}</span>
        </div>
        <div class="sev-detail-item sev-detail-wide">
          <span class="sev-detail-label">Common violation</span>
          <span class="sev-detail-val">${sevEsc(vioType)}</span>
        </div>
      </div>

      <div class="popup-scores">
        <div class="popup-score ${model === 'lightgbm' ? 'active-score' : ''}">
          <span class="score-label">LightGBM</span>
          <span class="score-val">${loc.lightgbm_prediction.toFixed(4)}</span>
        </div>
        <div class="popup-score ${model === 'baseline' ? 'active-score' : ''}">
          <span class="score-label">Baseline</span>
          <span class="score-val">${loc.baseline_prediction.toFixed(4)}</span>
        </div>
        <div class="popup-score ${model === 'naive'    ? 'active-score' : ''}">
          <span class="score-label">Naive</span>
          <span class="score-val">${loc.naive_prediction.toFixed(4)}</span>
        </div>
      </div>
      <div class="popup-risk-bar">
        <div class="popup-risk-fill" style="width:${pct}%;background:${color}"></div>
      </div>
      <div class="popup-risk-label">Severity: ${pct}% of max</div>
    </div>`;
}

/* ── Top-20 list ────────────────────────────────────────────────── */
function updateSevTop5() {
  const list = document.getElementById('sev-top5-list');
  if (!list) return;
  const model    = sevState.selectedModel;
  const key      = sevScoreKey(model);
  const top20    = [...sevState.predictions].sort((a, b) => (b[key] || 0) - (a[key] || 0)).slice(0, 20);
  
  const rawMaxScore = Math.max(...sevState.predictions.map(p => p[key] || 0));
  const effectiveMax = Math.max(rawMaxScore, 1e-6);

  const vehLabel = {
    two_wheeler:  '2W', auto_rickshaw: 'Auto', car: 'Car',
    lcv: 'LCV', bus: 'Bus', heavy_truck: 'HGV', tractor: 'Tractor',
  };

  list.innerHTML = top20.map((loc, i) => {
    const score = loc[key] || 0;
    const pct   = effectiveMax > 0 ? ((score / effectiveMax) * 100).toFixed(0) : 0;
    const color = sevRiskColor(score / effectiveMax);
    const veh   = vehLabel[loc.dominant_vehicle_cat] || (loc.dominant_vehicle_cat || '');
    const lane  = loc.lane_count != null ? `${loc.lane_count.toFixed(1)}L` : '';
    const meta2 = [veh, lane].filter(Boolean).join(' · ');
    return `
      <li class="top5-item">
        <div class="top5-rank" style="background:${color}">${i + 1}</div>
        <div class="top5-info">
          <div class="top5-name">${sevEsc(loc.location_key.replace(/^[A-Z0-9]+ - /, ''))}</div>
          <div class="top5-meta">${sevEsc(loc.area || '')} · ${sevEsc(meta2)}</div>
        </div>
        <div class="top5-score-wrap">
          <div class="top5-score">${score.toFixed(3)}</div>
          <div class="top5-bar-wrap">
            <div class="top5-bar" style="width:${pct}%;background:${color}"></div>
          </div>
        </div>
      </li>`;
  }).join('');
}

/* ── Stats ──────────────────────────────────────────────────────── */
function updateSevStats() {
  const preds    = sevState.predictions;
  const model    = sevState.selectedModel;
  const key      = sevScoreKey(model);
  const scores   = preds.map(p => p[key] || 0);
  const max      = Math.max(...scores);
  const disp     = Math.min(preds.length, SEV_TOP_N_ALWAYS_SHOW);

  const el = id => document.getElementById(id);
  if (el('sev-stat-locs')) el('sev-stat-locs').textContent = preds.length.toLocaleString();
  if (el('sev-stat-max'))  el('sev-stat-max').textContent  = max.toFixed(3);
  if (el('sev-stat-disp')) el('sev-stat-disp').textContent = disp.toLocaleString();
}

/* ── Model toggle ───────────────────────────────────────────────── */
function setupSevModelToggle() {
  document.querySelectorAll('#sev-model-toggle-row .model-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#sev-model-toggle-row .model-btn')
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      sevState.selectedModel = btn.dataset.model;
      if (sevState.predictions.length) {
        updateSevMapMarkers();
        updateSevTop5();
        updateSevStats();
      }
    });
  });
}

/* ── Page init (called once by router) ─────────────────────────── */
function initSeverityPage() {
  if (sevState.initialized) {
    if (sevState.sevMap) sevState.sevMap.invalidateSize();
    return;
  }
  sevState.initialized = true;

  // ── Leaflet map ───────────────────────────────────────────────
  sevState.renderer = L.canvas({ padding: 0.5 });
  sevState.sevMap   = L.map('sev-map', {
    center:       SEV_CENTER,
    zoom:         11,
    preferCanvas: true,
    zoomControl:  false,
  });
  L.control.zoom({ position: 'bottomright' }).addTo(sevState.sevMap);

  // Slightly different dark tile (still CartoDB dark, but consistent)
  L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { attribution: '© OpenStreetMap © CARTO', maxZoom: 19 }
  ).addTo(sevState.sevMap);

  // ── Default timestamp ─────────────────────────────────────────
  const dtInput = document.getElementById('sev-datetime');
  if (dtInput) dtInput.value = sevToDatetimeLocalValue(sevDefaultDatetime());

  // ── Run button ────────────────────────────────────────────────
  const runBtn = document.getElementById('sev-run');
  if (runBtn) runBtn.addEventListener('click', runSevPrediction);

  // ── Model toggle ──────────────────────────────────────────────
  setupSevModelToggle();

  // ── API health + confidence banner ───────────────────────────
  checkSevApiHealth();
}
