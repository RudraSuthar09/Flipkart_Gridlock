/* ═══════════════════════════════════════════════════════
   CONSTANTS & STATE
═══════════════════════════════════════════════════════ */
const DATA_URL = 'public/data/points.json';
const BENGALURU_CENTER = [12.9716, 77.5946];
const DOT_ALPHA = 0.18;

const MONTH_NAMES = [
  '', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

const BASEMAPS = {
  dark: {
    label: 'Dark',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    options: { attribution: '© OpenStreetMap © CARTO', maxZoom: 19 },
  },
  light: {
    label: 'Light',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    options: { attribution: '© OpenStreetMap © CARTO', maxZoom: 19 },
  },
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    options: { attribution: 'Tiles © Esri', maxZoom: 19 },
  },
  voyager: {
    label: 'Voyager',
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    options: { attribution: '© OpenStreetMap © CARTO', maxZoom: 19 },
  },
};

const state = {
  allPoints: [],
  filters: { year: null, month: null, day: null, hour: null, station: '', area: '' },
  mapInitialized: false,
};

/* ═══════════════════════════════════════════════════════
   UTILITIES
═══════════════════════════════════════════════════════ */
function fmt(n) { return new Intl.NumberFormat('en-IN').format(n || 0); }

function uniqueSorted(points, key) {
  return [...new Set(points.map(p => p[key]).filter(v => v != null))].sort((a, b) => a - b);
}

function countBy(points, key) {
  const map = new Map();
  points.forEach(p => {
    const v = p[key];
    if (v != null) map.set(v, (map.get(v) || 0) + 1);
  });
  return map;
}

function aggregatePoints(points) {
  const grouped = new Map();
  points.forEach(p => {
    const key = `${p.lat.toFixed(6)},${p.lng.toFixed(6)}`;
    const ex = grouped.get(key);
    if (ex) { ex.count++; ex.samples.push(p); }
    else grouped.set(key, { count: 1, lat: p.lat, lng: p.lng, samples: [p] });
  });
  return Array.from(grouped.values());
}

function escHtml(v) {
  return String(v ?? '—')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ═══════════════════════════════════════════════════════
   ROUTER
═══════════════════════════════════════════════════════ */
const pages = {
  home:           document.getElementById('page-home'),
  pastData:       document.getElementById('page-past-data'),
  onlyPrediction: document.getElementById('page-only-prediction'),
  severity:       document.getElementById('page-traffic-severity'),
};

function showPage(name) {
  Object.values(pages).forEach(p => p && (p.hidden = true));
  if (pages[name]) pages[name].hidden = false;

  if (name === 'pastData') {
    initMapPage();
  }
  if (name === 'onlyPrediction') {
    if (typeof initPredPage === 'function') initPredPage();
  }
  if (name === 'severity') {
    if (typeof initSeverityPage === 'function') initSeverityPage();
  }
}

function getRoute() {
  const hash = window.location.hash || '#/';
  if (hash === '#/past-data')          return 'pastData';
  if (hash === '#/only-prediction')    return 'onlyPrediction';
  if (hash === '#/traffic-severity')   return 'severity';
  return 'home';
}

window.addEventListener('hashchange', () => showPage(getRoute()));
window.addEventListener('DOMContentLoaded', () => {
  loadDataForHomeStats();
  showPage(getRoute());
});

/* ═══════════════════════════════════════════════════════
   HOME PAGE — quick stats
═══════════════════════════════════════════════════════ */
function loadDataForHomeStats() {
  fetch(DATA_URL)
    .then(r => r.json())
    .then(points => {
      state.allPoints = points;
      const areas   = new Set(points.map(p => p.area).filter(Boolean));
      const stations = new Set(points.map(p => p.police_station).filter(Boolean));
      document.getElementById('hs-total').textContent    = fmt(points.length);
      document.getElementById('hs-areas').textContent    = fmt(areas.size);
      document.getElementById('hs-stations').textContent = fmt(stations.size);
    })
    .catch(() => {});
}

/* ═══════════════════════════════════════════════════════
   CANVAS LAYER
═══════════════════════════════════════════════════════ */
let map = null;
let tileLayer = null;
let canvasLayer = null;

const ViolationCanvasLayer = L.Layer.extend({
  initialize(onClickCb) {
    this.points = [];
    this.canvas = null;
    this.frame = null;
    this._onClickCb = onClickCb;
    this.clickHandler = this.handleClick.bind(this);
  },
  onAdd(m) {
    this.map = m;
    this.canvas = L.DomUtil.create('canvas', 'violation-canvas leaflet-zoom-animated');
    this.context = this.canvas.getContext('2d', { alpha: true });
    m.getPanes().overlayPane.appendChild(this.canvas);
    m.on('move zoom resize viewreset', this.scheduleRedraw, this);
    m.on('click', this.clickHandler);
    this.redraw();
  },
  onRemove(m) {
    m.off('move zoom resize viewreset', this.scheduleRedraw, this);
    m.off('click', this.clickHandler);
    if (this.frame) L.Util.cancelAnimFrame(this.frame);
    L.DomUtil.remove(this.canvas);
    this.canvas = null; this.context = null; this.map = null;
  },
  setPoints(pts) { this.points = pts; this.scheduleRedraw(); },
  scheduleRedraw() {
    if (this.frame) return;
    this.frame = L.Util.requestAnimFrame(() => { this.frame = null; this.redraw(); });
  },
  redraw() {
    if (!this.map || !this.canvas || !this.context) return;
    const size = this.map.getSize();
    const px = window.devicePixelRatio || 1;
    const topLeft = this.map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(this.canvas, topLeft);
    this.canvas.width = size.x * px;
    this.canvas.height = size.y * px;
    this.canvas.style.width = `${size.x}px`;
    this.canvas.style.height = `${size.y}px`;
    const ctx = this.context;
    ctx.setTransform(px, 0, 0, px, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);
    const bounds = this.map.getBounds().pad(0.05);
    const zoom = this.map.getZoom();
    const radius = Math.max(2, Math.min(5, zoom * 0.27));
    this.points.forEach(pt => {
      if (!bounds.contains([pt.lat, pt.lng])) return;
      const cp = this.map.latLngToContainerPoint([pt.lat, pt.lng]);
      const alpha = Math.min(0.95, 1 - Math.pow(1 - DOT_ALPHA, pt.count));
      const g = ctx.createRadialGradient(cp.x, cp.y, 0, cp.x, cp.y, radius * 2.5);
      g.addColorStop(0, `rgba(255,80,80,${alpha})`);
      g.addColorStop(1, `rgba(255,40,40,0)`);
      ctx.beginPath(); ctx.fillStyle = g;
      ctx.arc(cp.x, cp.y, radius * 2.5, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.fillStyle = `rgba(255,100,100,${Math.min(1, alpha + 0.3)})`;
      ctx.arc(cp.x, cp.y, radius, 0, Math.PI * 2); ctx.fill();
    });
  },
  handleClick(event) {
    if (!this.map || !this.points.length) return;
    const cp = this.map.latLngToContainerPoint(event.latlng);
    let nearest = null, nearestDist = Infinity;
    this.points.forEach(pt => {
      const d = cp.distanceTo(this.map.latLngToContainerPoint([pt.lat, pt.lng]));
      if (d <= 12 && d < nearestDist) { nearest = pt; nearestDist = d; }
    });
    if (nearest && this._onClickCb) this._onClickCb(nearest);
  },
});

/* ═══════════════════════════════════════════════════════
   MAP PAGE INIT (runs once)
═══════════════════════════════════════════════════════ */
function initMapPage() {
  if (state.mapInitialized) { applyFilters(); return; }
  state.mapInitialized = true;

  // Init Leaflet map
  map = L.map('map', { center: BENGALURU_CENTER, zoom: 11, preferCanvas: true, zoomControl: false });
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  tileLayer = L.tileLayer(BASEMAPS.dark.url, BASEMAPS.dark.options).addTo(map);

  canvasLayer = new ViolationCanvasLayer(openDetailPanel);
  canvasLayer.addTo(map);

  // Basemap select
  const basemapEl = document.getElementById('basemap-select');
  Object.entries(BASEMAPS).forEach(([k, v]) => {
    const opt = document.createElement('option');
    opt.value = k; opt.textContent = v.label;
    basemapEl.appendChild(opt);
  });
  basemapEl.value = 'dark';
  basemapEl.addEventListener('change', () => {
    const bm = BASEMAPS[basemapEl.value] || BASEMAPS.dark;
    if (tileLayer) map.removeLayer(tileLayer);
    tileLayer = L.tileLayer(bm.url, bm.options).addTo(map);
    tileLayer.bringToBack();
  });

  // Close detail panel
  document.getElementById('detail-close').addEventListener('click', closeDetailPanel);

  // Station / area dropdowns
  document.getElementById('station-filter').addEventListener('change', e => {
    state.filters.station = e.target.value;
    applyFilters();
  });
  document.getElementById('area-filter').addEventListener('change', e => {
    state.filters.area = e.target.value;
    applyFilters();
  });

  // Clear all
  document.getElementById('clear-filters').addEventListener('click', () => {
    state.filters = { year: null, month: null, day: null, hour: null, station: '', area: '' };
    document.getElementById('station-filter').value = '';
    document.getElementById('area-filter').value = '';
    renderChips();
    applyFilters();
    updateClearBtn();
  });

  // Load data if not already loaded
  if (state.allPoints.length) {
    onDataReady();
  } else {
    document.getElementById('load-state-text').textContent = 'Loading map data…';
    document.getElementById('progress-fill').style.width = '30%';
    fetch(DATA_URL)
      .then(r => { if (!r.ok) throw new Error('Failed to load data'); return r.json(); })
      .then(pts => {
        state.allPoints = pts;
        document.getElementById('progress-fill').style.width = '100%';
        onDataReady();
      })
      .catch(err => {
        document.getElementById('error-state').hidden = false;
        document.getElementById('error-state').textContent = '⚠ ' + err.message;
        document.getElementById('load-state-text').textContent = 'Data load failed.';
      });
  }
}

/* ═══════════════════════════════════════════════════════
   DATA READY — populate dropdowns + chips
═══════════════════════════════════════════════════════ */
function onDataReady() {
  const pts = state.allPoints;

  // Populate station dropdown
  const stationEl = document.getElementById('station-filter');
  const stations = [...new Set(pts.map(p => p.police_station).filter(Boolean))].sort();
  stations.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s; opt.textContent = s;
    stationEl.appendChild(opt);
  });

  // Populate area dropdown
  const areaEl = document.getElementById('area-filter');
  const areas = [...new Set(pts.map(p => p.area).filter(Boolean))].sort();
  areas.forEach(a => {
    const opt = document.createElement('option');
    opt.value = a; opt.textContent = a;
    areaEl.appendChild(opt);
  });

  renderChips();
  applyFilters();
}

/* ═══════════════════════════════════════════════════════
   CHIP RENDERING
═══════════════════════════════════════════════════════ */
function pointsMatchingUpTo(level) {
  // level: 'year' | 'month' | 'day' | 'hour'
  return state.allPoints.filter(p => {
    if (level === 'year')  return true;
    if (state.filters.year  != null && p.year  !== state.filters.year)  return false;
    if (level === 'month') return true;
    if (state.filters.month != null && p.month !== state.filters.month) return false;
    if (level === 'day')   return true;
    if (state.filters.day   != null && p.day   !== state.filters.day)   return false;
    return true;
  });
}

function buildChips(containerId, wrapId, values, countMap, selected, key) {
  const wrap = document.getElementById(wrapId);
  const row  = document.getElementById(containerId);
  row.innerHTML = '';

  if (values.length === 0) { wrap.hidden = true; return; }
  wrap.hidden = false;

  // "All" chip
  const allBtn = document.createElement('button');
  allBtn.className = 'chip' + (selected === null ? ' active' : '');
  allBtn.textContent = 'All';
  allBtn.addEventListener('click', () => {
    state.filters[key] = null;
    cascadeReset(key);
    renderChips();
    applyFilters();
    updateClearBtn();
  });
  row.appendChild(allBtn);

  values.forEach(v => {
    const btn = document.createElement('button');
    btn.className = 'chip' + (selected === v ? ' active' : '');
    let label = String(v);
    if (key === 'month') label = MONTH_NAMES[v] || v;
    if (key === 'hour')  label = String(v).padStart(2, '0') + ':00';
    const cnt = countMap.get(v) || 0;
    btn.innerHTML = `${label}<span class="chip-count">${fmt(cnt)}</span>`;
    btn.addEventListener('click', () => {
      state.filters[key] = v;
      cascadeReset(key);
      renderChips();
      applyFilters();
      updateClearBtn();
    });
    row.appendChild(btn);
  });
}

function cascadeReset(changedKey) {
  const order = ['year', 'month', 'day', 'hour'];
  const idx = order.indexOf(changedKey);
  for (let i = idx + 1; i < order.length; i++) {
    state.filters[order[i]] = null;
  }
}

function renderChips() {
  const { year, month, day, hour } = state.filters;
  const all = state.allPoints;

  // Year
  const yearPts = all;
  const yearCounts = countBy(yearPts, 'year');
  buildChips('chips-year', 'wrap-year', uniqueSorted(all, 'year'), yearCounts, year, 'year');

  // Month (only if year selected)
  if (year !== null) {
    const byYear = all.filter(p => p.year === year);
    const monthCounts = countBy(byYear, 'month');
    buildChips('chips-month', 'wrap-month', uniqueSorted(byYear, 'month'), monthCounts, month, 'month');
  } else {
    document.getElementById('wrap-month').hidden = true;
    document.getElementById('wrap-day').hidden   = true;
    document.getElementById('wrap-hour').hidden  = true;
    return;
  }

  // Day (only if month selected)
  if (month !== null) {
    const byYM = all.filter(p => p.year === year && p.month === month);
    const dayCounts = countBy(byYM, 'day');
    buildChips('chips-day', 'wrap-day', uniqueSorted(byYM, 'day'), dayCounts, day, 'day');
  } else {
    document.getElementById('wrap-day').hidden   = true;
    document.getElementById('wrap-hour').hidden  = true;
    return;
  }

  // Hour (only if day selected)
  if (day !== null) {
    const byYMD = all.filter(p => p.year === year && p.month === month && p.day === day);
    const hourCounts = countBy(byYMD, 'hour');
    buildChips('chips-hour', 'wrap-hour', uniqueSorted(byYMD, 'hour'), hourCounts, hour, 'hour');
  } else {
    document.getElementById('wrap-hour').hidden = true;
  }
}

/* ═══════════════════════════════════════════════════════
   APPLY FILTERS & UPDATE MAP
═══════════════════════════════════════════════════════ */
function applyFilters() {
  const { year, month, day, hour, station, area } = state.filters;
  const filtered = state.allPoints.filter(p => {
    if (year    != null && p.year    !== year)    return false;
    if (month   != null && p.month   !== month)   return false;
    if (day     != null && p.day     !== day)      return false;
    if (hour    != null && p.hour    !== hour)     return false;
    if (station && p.police_station !== station)   return false;
    if (area    && p.area           !== area)      return false;
    return true;
  });

  const agg = aggregatePoints(filtered);
  if (canvasLayer) canvasLayer.setPoints(agg);

  document.getElementById('total-count').textContent    = fmt(state.allPoints.length);
  document.getElementById('filtered-count').textContent = fmt(filtered.length);
  document.getElementById('dot-count').textContent      = fmt(agg.length);
  document.getElementById('load-state-text').textContent =
    `${fmt(filtered.length)} records → ${fmt(agg.length)} clusters`;

  // Breadcrumb
  const bc = document.getElementById('filter-breadcrumb');
  const parts = [
    year  != null ? String(year) : null,
    month != null ? MONTH_NAMES[month] : null,
    day   != null ? `Day ${day}` : null,
    hour  != null ? String(hour).padStart(2, '0') + ':00' : null,
  ].filter(Boolean);
  if (parts.length) {
    bc.textContent = '📅 ' + parts.join(' › ');
    bc.hidden = false;
  } else {
    bc.hidden = true;
  }
}

function updateClearBtn() {
  const { year, month, day, hour, station, area } = state.filters;
  const hasFilter = year != null || station || area;
  document.getElementById('clear-filters').hidden = !hasFilter;
}

/* ═══════════════════════════════════════════════════════
   DETAIL PANEL
═══════════════════════════════════════════════════════ */
function openDetailPanel(cluster) {
  const panel = document.getElementById('detail-panel');
  const sample = cluster.samples[0] || {};
  const count  = cluster.count;

  // Count badge
  document.getElementById('dp-count').textContent = fmt(count);
  document.getElementById('dp-count-label').textContent =
    `violation${count > 1 ? 's' : ''} at this spot`;

  // Location grid
  document.getElementById('dp-location').innerHTML = gridRows([
    ['Area',       sample.area        || '—'],
    ['Pincode',    sample.pincode     || '—'],
    ['Police Stn', sample.police_station || '—'],
    ['Coords',     `${Number(cluster.lat).toFixed(5)}, ${Number(cluster.lng).toFixed(5)}`],
  ]);

  // Time grid
  const timeStr = [sample.date_label, sample.time_label].filter(Boolean).join(' ');
  document.getElementById('dp-time').innerHTML = gridRows([
    ['Date/Time', timeStr || '—'],
    ['Year',      sample.year  ?? '—'],
    ['Month',     MONTH_NAMES[sample.month] || sample.month || '—'],
  ]);

  // Violation
  const viol = sample.violation || '';
  const parts = viol.split('--');
  const vLabel = parts[0]?.trim() || viol;
  const vCode  = parts[1] ? `#${parts[1].trim()}` : '';
  const violList = document.getElementById('dp-violations');
  if (viol) {
    violList.innerHTML = `
      <li class="violation-tag">
        <span class="v-code">${escHtml(vCode)}</span>
        <span class="v-label">${escHtml(vLabel)}</span>
      </li>`;
  } else {
    violList.innerHTML = '<li style="color:var(--text-3);font-size:12px;font-style:italic;">No violation flag</li>';
  }

  // Mini records (if cluster > 1)
  const recSection = document.getElementById('dp-records-section');
  if (count > 1) {
    document.getElementById('dp-records-title').textContent =
      `All Records Here (${fmt(count)})`;
    const mini = document.getElementById('dp-records');
    mini.innerHTML = cluster.samples.slice(0, 8).map((s, i) => `
      <div class="mini-record">
        <span class="mini-id">${escHtml(s.date_label || ('#' + (i+1)))}</span>
        <span class="mini-info">${escHtml((s.violation || '').split('--')[0].slice(0, 30) || '—')}</span>
      </div>`).join('');
    if (count > 8) {
      mini.innerHTML += `<p class="mini-more">+${fmt(count - 8)} more records</p>`;
    }
    recSection.hidden = false;
  } else {
    recSection.hidden = true;
  }

  panel.hidden = false;
  // Restart animation
  panel.style.animation = 'none';
  panel.offsetHeight; // reflow
  panel.style.animation = '';
}

function gridRows(rows) {
  return rows.map(([k, v]) =>
    `<span class="dk">${escHtml(k)}</span><span class="dv">${escHtml(v)}</span>`
  ).join('');
}

function closeDetailPanel() {
  document.getElementById('detail-panel').hidden = true;
}
