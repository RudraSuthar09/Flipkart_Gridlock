/* ═══════════════════════════════════════════════════════
   only_prediction.js — Predictive Heatmap page
   Route: #/only-prediction
   API:   http://127.0.0.1:8001/api/v1
═══════════════════════════════════════════════════════ */

const API_BASE = 'http://127.0.0.1:8001/api/v1';
const PRED_CENTER = [12.9716, 77.5946];

// Always render the top N locations regardless of score magnitude.
// Rank-based display is robust against heavy-tailed distributions where
// a single dominant hotspot inflates any relative percentage threshold.
const DISPLAY_TOP_N = 100;

/* ── State ─────────────────────────────────────────── */
const predState = {
  predictions:   [],   // raw API response array (all locations, all 3 scores)
  selectedModel: 'lightgbm',
  predMap:       null,
  markerLayer:   null,
  renderer:      null,
  initialized:   false,
  loading:       false,
};

/* ── Color helpers ──────────────────────────────────── */
function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function lerpColor(hex1, hex2, t) {
  const [r1, g1, b1] = hexToRgb(hex1);
  const [r2, g2, b2] = hexToRgb(hex2);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  return `rgb(${r},${g},${b})`;
}

/**
 * Map a normalised risk score [0..1] to a color.
 * 0.0 → green (#22c55e)
 * 0.5 → amber (#f59e0b)
 * 1.0 → red   (#ef4444)
 */
function riskColor(ratio) {
  if (ratio <= 0) return '#22c55e';
  if (ratio >= 1) return '#ef4444';
  if (ratio < 0.5) return lerpColor('#22c55e', '#f59e0b', ratio * 2);
  return lerpColor('#f59e0b', '#ef4444', (ratio - 0.5) * 2);
}

/* ── Datetime helpers ───────────────────────────────── */
function toDatetimeLocalValue(d) {
  // Returns "YYYY-MM-DDTHH:MM" for datetime-local input
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

function defaultDatetime() {
  // Default = current hour
  const now = new Date();
  now.setMinutes(0, 0, 0);
  return now;
}

/* ── API helpers ────────────────────────────────────── */
function setApiStatus(state, msg) {
  const dot  = document.getElementById('pred-api-dot');
  const text = document.getElementById('pred-api-text');
  if (!dot || !text) return;
  dot.className  = `api-dot api-dot-${state}`;   // ok | loading | error
  text.textContent = msg;
}

async function checkApiHealth() {
  setApiStatus('loading', 'Connecting to API…');
  try {
    const res  = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(6000) });
    const data = await res.json();
    if (data.status === 'ok' && data.model_loaded) {
      setApiStatus('ok', `API ready · ${data.location_count.toLocaleString()} locations`);

      // ── Set the default datetime to the last timestamp in the panel.
      // The dataset ends in 2024; defaulting to "now" (2026) gives zero lookback
      // features, so every location scores near-zero and nothing renders on the map.
      if (data.panel_last_updated) {
        const dtInput = document.getElementById('pred-datetime');
        if (dtInput) {
          const panelEnd = new Date(data.panel_last_updated.replace(' ', 'T'));
          panelEnd.setMinutes(0, 0, 0);
          dtInput.value = toDatetimeLocalValue(panelEnd);
        }
      }
    } else {
      setApiStatus('error', 'API up but model not loaded');
    }
  } catch {
    setApiStatus('error', 'Cannot reach API (port 8001)');
  }
}

/* ── Loading overlay ───────────────────────────────── */
function setLoading(on, msg) {
  const overlay = document.getElementById('pred-loading');
  const text    = document.getElementById('pred-loading-text');
  if (!overlay) return;
  // Use style.display directly — CSS class display:flex would override the
  // hidden HTML attribute, keeping the overlay on screen even after done.
  overlay.style.display = on ? 'flex' : 'none';
  if (text && msg) text.textContent = msg;
  predState.loading = on;
}

/* ── Run prediction ─────────────────────────────────── */
async function runPrediction() {
  if (predState.loading) return;
  const dtInput = document.getElementById('pred-datetime');
  if (!dtInput || !dtInput.value) {
    alert('Please pick a target date & hour first.');
    return;
  }

  const ts = dtInput.value;   // "YYYY-MM-DDTHH:MM"
  setLoading(true, 'Fetching predictions…');
  setApiStatus('loading', 'Predicting…');

  try {
    const url = `${API_BASE}/predict?timestamp=${encodeURIComponent(ts)}`;
    const res  = await fetch(url, { signal: AbortSignal.timeout(60000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    predState.predictions = await res.json();

    setApiStatus('ok', `Done · ${predState.predictions.length.toLocaleString()} locations`);
    updateMapMarkers();
    updateTop5();
    updateStats();
  } catch (err) {
    setApiStatus('error', 'Prediction failed: ' + err.message);
    console.error(err);
  } finally {
    setLoading(false);
  }
}

/* ── Map markers ────────────────────────────────────── */
function scoreKey(model) { return `${model}_prediction`; }

function computeRanks(preds, model) {
  const key  = scoreKey(model);
  const sorted = [...preds].sort((a, b) => b[key] - a[key]);
  const rankMap = new Map();
  sorted.forEach((p, i) => rankMap.set(p.location_key, i + 1));
  return rankMap;
}

function updateMapMarkers() {
  if (!predState.predMap) return;
  const preds = predState.predictions;
  const model = predState.selectedModel;
  const key   = scoreKey(model);

  const rawMaxScore = Math.max(...preds.map(p => p[key] || 0));
  const effectiveMax = Math.max(rawMaxScore, 1e-6);

  // Always render top N by rank — robust against heavy-tailed score distributions.
  const sorted  = [...preds].sort((a, b) => (b[key] || 0) - (a[key] || 0));
  const rankMap = new Map(sorted.map((p, i) => [p.location_key, i + 1]));
  const visible = sorted.slice(0, DISPLAY_TOP_N);

  // Clear old markers
  if (predState.markerLayer) {
    predState.predMap.removeLayer(predState.markerLayer);
  }
  predState.markerLayer = L.layerGroup();

  visible.forEach(loc => {
    const score  = loc[key] || 0;
    const ratio  = effectiveMax > 0 ? score / effectiveMax : 0;
    const rank   = rankMap.get(loc.location_key);
    const isTop20 = rank <= 20;
    const color  = riskColor(ratio);

    const marker = L.circleMarker(
      [loc.latitude, loc.longitude],
      {
        renderer:    predState.renderer,
        radius:      isTop20 ? 9 : (ratio > 0.3 ? 6 : 5),
        fillColor:   color,
        fillOpacity: isTop20 ? 1 : 0.8,
        color:       isTop20 ? '#ffffff' : color,
        weight:      isTop20 ? 2 : 0,
        bubblingMouseEvents: false,
      }
    );

    marker.bindPopup(buildPopup(loc, rank, model, score, effectiveMax), { maxWidth: 280 });
    predState.markerLayer.addLayer(marker);
  });

  predState.markerLayer.addTo(predState.predMap);

  // Update displayed count in stats
  const dispEl = document.getElementById('pred-stat-disp');
  if (dispEl) dispEl.textContent = visible.length.toLocaleString();
}

function buildPopup(loc, rank, model, score, effectiveMax) {
  const pct = effectiveMax > 0 ? ((score / effectiveMax) * 100).toFixed(1) : '0.0';
  const isTop5 = rank <= 5;
  const badge  = isTop5
    ? `<span class="popup-rank-badge popup-rank-top">#${rank} HOTSPOT</span>`
    : `<span class="popup-rank-badge">#${rank}</span>`;

  return `
    <div class="pred-popup">
      ${badge}
      <div class="popup-loc">${esc(loc.location_key)}</div>
      <div class="popup-meta">
        <span>${esc(loc.area || '—')}</span>
        <span>${esc(loc.police_station || '—')}</span>
      </div>
      <div class="popup-scores">
        <div class="popup-score ${model === 'lightgbm'  ? 'active-score' : ''}">
          <span class="score-label">LightGBM</span>
          <span class="score-val">${loc.lightgbm_prediction.toFixed(4)}</span>
        </div>
        <div class="popup-score ${model === 'baseline'  ? 'active-score' : ''}">
          <span class="score-label">Baseline</span>
          <span class="score-val">${loc.baseline_prediction.toFixed(4)}</span>
        </div>
        <div class="popup-score ${model === 'naive'     ? 'active-score' : ''}">
          <span class="score-label">Naive</span>
          <span class="score-val">${loc.naive_prediction.toFixed(1)}</span>
        </div>
      </div>
      <div class="popup-risk-bar">
        <div class="popup-risk-fill" style="width:${pct}%;background:${riskColor(score / (effectiveMax || 1))}"></div>
      </div>
      <div class="popup-risk-label">Risk: ${pct}% of max</div>
    </div>`;
}

function esc(v) {
  return String(v ?? '—')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function updateTop5() {
  const list  = document.getElementById('pred-top5-list');
  if (!list) return;
  const model = predState.selectedModel;
  const key   = scoreKey(model);

  const top20 = [...predState.predictions]
    .sort((a, b) => (b[key] || 0) - (a[key] || 0))
    .slice(0, 20);

  const rawMaxScore = Math.max(...predState.predictions.map(p => p[key] || 0));
  const effectiveMax = Math.max(rawMaxScore, 1e-6);

  list.innerHTML = top20.map((loc, i) => {
    const score = loc[key] || 0;
    const pct   = effectiveMax > 0 ? ((score / effectiveMax) * 100).toFixed(0) : 0;
    const color = riskColor(score / effectiveMax);
    return `
      <li class="top5-item">
        <div class="top5-rank" style="background:${color}">${i + 1}</div>
        <div class="top5-info">
          <div class="top5-name">${esc(loc.location_key.replace(/^[A-Z0-9]+ - /, ''))}</div>
          <div class="top5-meta">${esc(loc.area || '')} · ${esc(loc.police_station || '')}</div>
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

/* ── Stats ──────────────────────────────────────────── */
function updateStats() {
  const preds = predState.predictions;
  const model = predState.selectedModel;
  const key   = scoreKey(model);
  const scores = preds.map(p => p[key] || 0);
  const max    = Math.max(...scores);
  const disp   = Math.min(preds.length, DISPLAY_TOP_N);

  const el = id => document.getElementById(id);
  if (el('pred-stat-locs')) el('pred-stat-locs').textContent = preds.length.toLocaleString();
  if (el('pred-stat-max'))  el('pred-stat-max').textContent  = max.toFixed(3);
  if (el('pred-stat-disp')) el('pred-stat-disp').textContent = disp.toLocaleString();
}

/* ── Model toggle ───────────────────────────────────── */
function setupModelToggle() {
  document.querySelectorAll('.model-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.model-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      predState.selectedModel = btn.dataset.model;
      if (predState.predictions.length) {
        updateMapMarkers();
        updateTop5();
        updateStats();
      }
    });
  });
}

/* ── Page init (called once by router) ─────────────── */
function initPredPage() {
  if (predState.initialized) {
    // Already up: just ensure map re-draws after hidden/show cycle
    if (predState.predMap) predState.predMap.invalidateSize();
    return;
  }
  predState.initialized = true;

  // ── Leaflet map ──────────────────────────────────
  predState.renderer = L.canvas({ padding: 0.5 });
  predState.predMap  = L.map('pred-map', {
    center:       PRED_CENTER,
    zoom:         11,
    preferCanvas: true,
    zoomControl:  false,
  });
  L.control.zoom({ position: 'bottomright' }).addTo(predState.predMap);

  // Dark basemap tile
  L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { attribution: '© OpenStreetMap © CARTO', maxZoom: 19 }
  ).addTo(predState.predMap);

  // ── Default timestamp (current hour) ─────────────
  const dtInput = document.getElementById('pred-datetime');
  if (dtInput) dtInput.value = toDatetimeLocalValue(defaultDatetime());

  // ── Run button ───────────────────────────────────
  const runBtn = document.getElementById('pred-run');
  if (runBtn) runBtn.addEventListener('click', runPrediction);

  // ── Model toggle ─────────────────────────────────
  setupModelToggle();

  // ── API health check ─────────────────────────────
  checkApiHealth();
}
