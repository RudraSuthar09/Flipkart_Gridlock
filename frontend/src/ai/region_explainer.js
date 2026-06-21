/* ══════════════════════════════════════════════════════
   Feature 3 — Map Region Drag-Select + AI Chat Panel
   Works on ALL map pages: Past Data, Prediction, Severity.

   initRegionExplainer(map, data, pageType)
     pageType: 'past-data' | 'prediction' | 'severity'

   Flow:
     1. "⬚ Select Region" button added via Leaflet Control.
     2. User drags a rectangle on the map.
     3. Panel slides in: junction list + multi-turn AI chat.
     4. Auto-generates first analysis; user can ask more Qs.
══════════════════════════════════════════════════════ */

// Per-map state (keyed by Leaflet's internal map ID)
const _reInst = new Map();

// ── Public entry point ────────────────────────────────
function initRegionExplainer(map, data, pageType) {
  const id = map._leaflet_id;

  if (_reInst.has(id)) {
    const inst = _reInst.get(id);
    if (Array.isArray(data) && data.length) {
      inst.data     = data;
      inst.pageType = pageType || inst.pageType;
      _reRefreshScoreKey(inst);
    }
    return;
  }

  const inst = {
    map,
    data:      Array.isArray(data) ? data : [],
    pageType:  pageType || 'prediction',
    scoreKey:  'lightgbm_prediction',
    panel:     null,
    drawn:     null,
    inDraw:    false,
    _btn:      null,
    _startLL:  null,
    _tempRect: null,
    history:   [],     // { role, html } per selection session
    ctx:       null,   // current region context string
  };
  _reRefreshScoreKey(inst);
  _reInst.set(id, inst);

  _reBuildPanel(inst);
  _reAddControl(inst);
}

// Allow data refresh without re-init (called after predictions run)
function _reUpdateData(map, newData) {
  const inst = _reInst.get(map._leaflet_id);
  if (!inst) return;
  inst.data = Array.isArray(newData) ? newData : [];
  _reRefreshScoreKey(inst);
}

function _reRefreshScoreKey(inst) {
  if (inst.pageType === 'past-data') { inst.scoreKey = 'count'; return; }
  // Try to pick up currently selected model from global state
  const model = (typeof predState !== 'undefined' && predState.selectedModel)
             || (typeof sevState  !== 'undefined' && sevState.selectedModel)
             || 'lightgbm';
  inst.scoreKey = `${model}_prediction`;
}

// ── Panel ─────────────────────────────────────────────
function _reBuildPanel(inst) {
  const mapEl = inst.map.getContainer();
  const wrap  = mapEl.parentElement;
  if (!wrap) return;
  const old = wrap.querySelector('.vm-rp-panel');
  if (old) old.remove();

  const panel = document.createElement('div');
  panel.className = 'vm-rp-panel';
  panel.innerHTML = _rePanelIdle();
  wrap.appendChild(panel);
  inst.panel = panel;
}

function _rePanelIdle() {
  return `
    <div class="vm-rp-idle">
      <div class="vm-rp-idle-icon">⬚</div>
      <p class="vm-rp-idle-text">Drag a rectangle on the map to analyse any region with AI</p>
    </div>`;
}

// ── Leaflet Control button ────────────────────────────
function _reAddControl(inst) {
  const Ctrl = L.Control.extend({
    options: { position: 'topleft' },
    onAdd: function () {
      const wrap = L.DomUtil.create('div', 'leaflet-bar leaflet-control vm-rp-ctrl');
      const btn  = L.DomUtil.create('button', 'vm-rp-toggle-btn', wrap);
      btn.innerHTML = '<span class="vm-rp-btn-icon">⬚</span> Select Region';
      btn.title = 'Drag on the map to select a region for AI analysis';
      L.DomEvent.disableClickPropagation(btn);
      L.DomEvent.on(btn, 'click', e => { L.DomEvent.stop(e); _reToggle(inst, btn); });
      inst._btn = btn;
      return wrap;
    },
  });
  new Ctrl().addTo(inst.map);
}

// ── Toggle draw mode ──────────────────────────────────
function _reToggle(inst, btn) {
  inst.inDraw = !inst.inDraw;
  if (inst.inDraw) {
    btn.classList.add('vm-rp-toggle-btn--active');
    btn.innerHTML = '<span class="vm-rp-btn-icon">✕</span> Cancel';
    _reEnableDrag(inst);
  } else {
    btn.classList.remove('vm-rp-toggle-btn--active');
    btn.innerHTML = '<span class="vm-rp-btn-icon">⬚</span> Select Region';
    _reDisableDrag(inst);
  }
}

// ── Drag-to-select ────────────────────────────────────
function _reEnableDrag(inst) {
  inst.map.getContainer().style.cursor = 'crosshair';
  inst.map.on('mousedown', inst._onDown = e => _reDown(inst, e));
}

function _reDisableDrag(inst) {
  inst.map.getContainer().style.cursor = '';
  inst.map.off('mousedown', inst._onDown);
  inst.map.off('mousemove', inst._onMove);
  inst.map.off('mouseup',   inst._onUp);
  if (inst._tempRect) { inst.map.removeLayer(inst._tempRect); inst._tempRect = null; }
}

function _reDown(inst, e) {
  inst._startLL = e.latlng;
  inst.map.dragging.disable();
  inst.map.on('mousemove', inst._onMove = e2 => _reMove(inst, e2));
  inst.map.once('mouseup', inst._onUp  = e2 => _reUp(inst, e2));
}

function _reMove(inst, e) {
  const b = L.latLngBounds(inst._startLL, e.latlng);
  if (!inst._tempRect) {
    inst._tempRect = L.rectangle(b, {
      color: '#6366f1', weight: 2, opacity: 0.9, fillOpacity: 0.06, dashArray: '5,4',
    }).addTo(inst.map);
  } else { inst._tempRect.setBounds(b); }
}

function _reUp(inst, e) {
  inst.map.off('mousemove', inst._onMove);
  inst.map.dragging.enable();
  // Remove the persistent mousedown listener so normal map dragging works again
  inst.map.off('mousedown', inst._onDown);
  inst.map.getContainer().style.cursor = '';
  inst.inDraw = false;
  if (inst._btn) {
    inst._btn.classList.remove('vm-rp-toggle-btn--active');
    inst._btn.innerHTML = '<span class="vm-rp-btn-icon">⬚</span> Select Region';
  }

  if (!inst._startLL) return;
  const bounds = L.latLngBounds(inst._startLL, e.latlng);
  const sw = inst.map.latLngToContainerPoint(bounds.getSouthWest());
  const ne = inst.map.latLngToContainerPoint(bounds.getNorthEast());

  if (Math.abs(sw.x - ne.x) + Math.abs(sw.y - ne.y) < 20) {
    if (inst._tempRect) { inst.map.removeLayer(inst._tempRect); inst._tempRect = null; }
    inst._startLL = null;
    return;
  }

  if (inst.drawn) inst.map.removeLayer(inst.drawn);
  inst.drawn    = inst._tempRect;
  inst._tempRect = null;
  if (inst.drawn) inst.drawn.setStyle({ dashArray: null, fillOpacity: 0.09 });
  inst._startLL = null;
  _reOnSelected(inst, bounds);
}

// ── Handle completed selection ────────────────────────
function _reOnSelected(inst, bounds) {
  _reRefreshScoreKey(inst);

  if (!inst.data.length) {
    _reOpenPanel(inst);
    _rePanelSetContent(inst, `
      <div class="vm-rp-idle">
        <div class="vm-rp-idle-icon">⏳</div>
        <p class="vm-rp-idle-text">Run a prediction first, then drag to analyse a region.</p>
      </div>`);
    return;
  }

  const result = _reExtract(inst, bounds);
  if (result.total < 2) {
    _reToast(inst, 'Drag a larger area — fewer than 2 hotspots inside');
    if (inst.drawn) { inst.map.removeLayer(inst.drawn); inst.drawn = null; }
    return;
  }

  inst.history = [];
  inst.ctx = _reContext(inst, result);

  _reOpenPanel(inst);
  _rePanelSetContent(inst, _rePanelContentHTML(inst, result));
  _reWirePanel(inst, result);

  // Auto-generate first analysis
  _reAutoAnalyse(inst, result);
}

// ── Extract region data ───────────────────────────────
function _reExtract(inst, bounds) {
  const inBounds = p =>
    p.latitude  >= bounds.getSouth() && p.latitude  <= bounds.getNorth() &&
    p.longitude >= bounds.getWest()  && p.longitude <= bounds.getEast();

  if (inst.pageType === 'past-data') {
    const inside = inst.data.filter(inBounds);
    const byArea = {};
    inside.forEach(p => {
      const k = p.police_station || p.area || 'Unknown';
      if (!byArea[k]) byArea[k] = { name: k, count: 0, vtypes: {} };
      byArea[k].count++;
      const vt = (p.violation || 'Other').split('--')[0].trim().slice(0, 30) || 'Other';
      byArea[k].vtypes[vt] = (byArea[k].vtypes[vt] || 0) + 1;
    });
    const top5 = Object.values(byArea)
      .sort((a, b) => b.count - a.count)
      .slice(0, 5)
      .map(a => ({ name: a.name, score: a.count, label: `${a.count} violations`,
                   detail: Object.entries(a.vtypes).sort((x,y) => y[1]-x[1])[0]?.[0] || '' }));
    return { top5, total: inside.length, raw: inside };
  } else {
    const inside = inst.data.filter(inBounds);
    const sorted = [...inside].sort((a, b) => (b[inst.scoreKey]||0) - (a[inst.scoreKey]||0));
    const top5 = sorted.slice(0, 5).map(p => ({
      name:   p.location_key || 'Unknown',
      score:  p[inst.scoreKey] || 0,
      label:  (p[inst.scoreKey] || 0).toFixed(3),
      detail: p.area || '',
    }));
    return { top5, total: inside.length, raw: inside };
  }
}

// ── Build context string for AI ───────────────────────
function _reContext(inst, result) {
  const pageLabel = { 'past-data': 'Past Violation Data', prediction: 'Predictive Heatmap', severity: 'Severity Heatmap' }[inst.pageType] || inst.pageType;
  const dtEl = document.getElementById('pred-datetime') || document.getElementById('sev-datetime');
  const ts   = dtEl ? dtEl.value : 'current time';
  const list = result.top5.map((t, i) => `${i+1}. ${t.name} (${t.label}${t.detail ? ', ' + t.detail : ''})`).join('; ');
  return `Page: ${pageLabel} | Time: ${ts} | Total in region: ${result.total} | Top locations: ${list}`;
}

// ── Panel HTML ────────────────────────────────────────
function _rePanelContentHTML(inst, result) {
  const maxScore = Math.max(...result.top5.map(t => t.score), 1e-9);
  const pageLabel = { 'past-data': 'Past Data', prediction: 'Prediction', severity: 'Severity' }[inst.pageType] || '';
  const badge = inst.pageType === 'past-data' ? 'violations' : 'hotspots';

  return `
    <div class="vm-rp-header">
      <div class="vm-rp-header-left">
        <span class="vm-rp-pin">📍</span>
        <div>
          <div class="vm-rp-title">Region Analysis</div>
          <div class="vm-rp-subtitle">${pageLabel} · ${result.total} ${badge}</div>
        </div>
      </div>
      <button class="vm-rp-close-btn" id="vm-rp-close">✕</button>
    </div>

    <div class="vm-rp-locations">
      <div class="vm-rp-section-label">TOP LOCATIONS</div>
      ${result.top5.map((t, i) => {
        const pct = ((t.score / maxScore) * 100).toFixed(0);
        return `
          <div class="vm-rp-loc-row">
            <span class="vm-rp-loc-rank">${String(i+1).padStart(2,'0')}</span>
            <div class="vm-rp-loc-info">
              <div class="vm-rp-loc-name">${_reEsc(t.name)}</div>
              ${t.detail ? `<div class="vm-rp-loc-detail">${_reEsc(t.detail)}</div>` : ''}
              <div class="vm-rp-loc-bar-wrap"><div class="vm-rp-loc-bar" style="width:${pct}%"></div></div>
            </div>
            <span class="vm-rp-loc-val">${_reEsc(t.label)}</span>
          </div>`;
      }).join('')}
    </div>

    <div class="vm-rp-chat">
      <div class="vm-rp-section-label">AI ANALYSIS</div>
      <div class="vm-rp-messages" id="vm-rp-msgs"></div>
      <div class="vm-rp-chips" id="vm-rp-chips">
        ${_reChips(inst.pageType).map(q => `<button class="vm-rp-chip" data-q="${_reEsc(q)}">${_reEsc(q)}</button>`).join('')}
      </div>
      <div class="vm-rp-input-row">
        <input id="vm-rp-input" class="vm-rp-input" placeholder="Ask anything about this area…" maxlength="250" autocomplete="off" />
        <button id="vm-rp-send" class="vm-rp-send">➤</button>
      </div>
    </div>`;
}

function _reChips(pageType) {
  if (pageType === 'past-data') return ['Why so many violations here?', 'Peak violation time?', 'Top violation type?', 'Enforcement plan?'];
  if (pageType === 'severity')  return ['Why is severity high here?', 'Emergency access risks?', 'Infrastructure gaps?', 'Patrol schedule?'];
  return ['Why are these high-risk?', 'What makes it worse at this hour?', 'Enforcement strategy?', 'Compare to rest of city'];
}

// ── Wire up panel interactivity ───────────────────────
function _reWirePanel(inst, result) {
  const panel = inst.panel;
  if (!panel) return;

  panel.querySelector('#vm-rp-close')
    ?.addEventListener('click', () => _reClosePanel(inst));

  panel.querySelectorAll('.vm-rp-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const input = panel.querySelector('#vm-rp-input');
      if (input) input.value = chip.dataset.q;
      _reSend(inst);
    });
  });

  panel.querySelector('#vm-rp-send')
    ?.addEventListener('click', () => _reSend(inst));

  panel.querySelector('#vm-rp-input')
    ?.addEventListener('keydown', e => {
      if (e.key === 'Enter') _reSend(inst);
    });
}

// ── Send a question ───────────────────────────────────
async function _reSend(inst) {
  const panel = inst.panel;
  const input = panel?.querySelector('#vm-rp-input');
  if (!input) return;

  const q = input.value.trim();
  if (!q || inst._sending) return;

  input.value  = '';
  inst._sending = true;

  _reAddMsg(inst, 'user', `<p class="vm-rp-msg-text">${_reEsc(q)}</p>`);

  const thinkId = _reAddMsg(inst, 'ai', _reThinkingHTML(), true);

  try {
    const histText = inst.history.slice(-6)
      .map(m => `${m.role === 'user' ? 'User' : 'AI'}: ${m.plain}`)
      .join('\n');

    const system = `You are a sharp Bengaluru traffic analyst. You are analysing a specific region the user selected on a live map dashboard.

Region context: ${inst.ctx}

${histText ? `Conversation so far:\n${histText}\n` : ''}

Format your response with these EXACT labels on their own lines:
**INSIGHT:** [1-2 sentences – the core finding]
**FACTORS:**
• [factor 1]
• [factor 2]
• [factor 3 if relevant]
**RECOMMENDATION:** [1-2 specific, actionable steps with timing/location details]

Be precise. Name specific junctions. Max 130 words total.`;

    const answer = await callGroqChat(system, q);
    inst.history.push({ role: 'user', plain: q });
    inst.history.push({ role: 'ai',   plain: answer });

    const formatted = _reFormat(answer);
    _reReplaceMsg(inst, thinkId, 'ai', formatted);
  } catch (err) {
    _reReplaceMsg(inst, thinkId, 'ai', '<p class="vm-rp-msg-text">Something went wrong — please try again.</p>');
  } finally {
    inst._sending = false;
  }
}

// ── Auto-generate initial analysis ───────────────────
async function _reAutoAnalyse(inst, result) {
  const thinkId = _reAddMsg(inst, 'ai', _reThinkingHTML(), true);
  inst._sending = true;

  try {
    const system = `You are a senior Bengaluru traffic analyst briefing officials. Analyse the selected map region.

Region context: ${inst.ctx}

Format EXACTLY as below — use these labels verbatim:
**INSIGHT:** [2 sentences – what makes this cluster noteworthy]
**FACTORS:**
• [main geographic/functional risk factor]
• [time-of-day or demand-side factor]
• [infrastructure or enforcement gap]
**RECOMMENDATION:** [2 specific, implementable actions with location + timing details]

Name actual junctions. Max 140 words total. Be direct, no filler.`;

    const q = `Give a complete analysis of this selected region — explain why it's high risk and what should be done.`;
    const answer = await callGroqChat(system, q);
    inst.history.push({ role: 'ai', plain: answer });

    const formatted = _reFormat(answer);
    _reReplaceMsg(inst, thinkId, 'ai', formatted);
  } catch {
    _reReplaceMsg(inst, thinkId, 'ai', '<p class="vm-rp-msg-text">Analysis failed — ask your own question below.</p>');
  } finally {
    inst._sending = false;
  }
}

// ── Format AI response into rich HTML ─────────────────
function _reFormat(raw) {
  const escape = s => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  const insightM = raw.match(/\*\*INSIGHT:\*\*\s*([\s\S]*?)(?=\*\*[A-Z]|$)/i);
  const factorsM = raw.match(/\*\*FACTORS?:\*\*\s*([\s\S]*?)(?=\*\*[A-Z]|$)/i);
  const recM     = raw.match(/\*\*RECOMMENDATION:\*\*\s*([\s\S]*?)(?=\*\*[A-Z]|$)/i);

  let html = '';

  if (insightM) {
    html += `<div class="vm-rp-insight">${escape(insightM[1].trim())}</div>`;
  }

  if (factorsM) {
    const bullets = factorsM[1].trim()
      .split('\n')
      .map(l => l.trim())
      .filter(l => l.startsWith('•') || l.startsWith('-') || l.startsWith('*'))
      .map(l => l.replace(/^[•\-*]\s*/, ''))
      .filter(Boolean);

    if (bullets.length) {
      html += `
        <div class="vm-rp-factors">
          <div class="vm-rp-block-label"><span class="vm-rp-block-icon">⚡</span> Risk Factors</div>
          <ul class="vm-rp-bullets">
            ${bullets.map(b => `<li>${escape(b)}</li>`).join('')}
          </ul>
        </div>`;
    }
  }

  if (recM) {
    const recText = recM[1].trim();
    html += `
      <div class="vm-rp-recommendation">
        <div class="vm-rp-block-label"><span class="vm-rp-block-icon">💡</span> Recommendation</div>
        <div class="vm-rp-rec-body">${escape(recText)}</div>
      </div>`;
  }

  // Fallback: no structure detected
  if (!html) {
    html = `<p class="vm-rp-msg-text">${escape(raw)}</p>`;
  }

  return html;
}

// ── Message rendering ─────────────────────────────────
let _reMsgId = 0;
function _reAddMsg(inst, role, html, returnsId) {
  const msgs = inst.panel?.querySelector('#vm-rp-msgs');
  if (!msgs) return;

  const id  = `vm-rp-msg-${++_reMsgId}`;
  const div = document.createElement('div');
  div.className = `vm-rp-msg vm-rp-msg--${role}`;
  div.id        = id;
  div.innerHTML = `
    <div class="vm-rp-msg-avatar">${role === 'ai' ? '🤖' : '👤'}</div>
    <div class="vm-rp-msg-body">${html}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;

  if (returnsId) return id;
}

function _reReplaceMsg(inst, id, role, html) {
  const msgs = inst.panel?.querySelector('#vm-rp-msgs');
  if (!msgs) return;
  const old = document.getElementById(id);
  if (old) old.remove();
  _reAddMsg(inst, role, html);
}

function _reThinkingHTML() {
  return `<div class="vm-rp-thinking"><span></span><span></span><span></span></div>`;
}

// ── Panel open / close ────────────────────────────────
function _reOpenPanel(inst) {
  if (inst.panel) inst.panel.classList.add('vm-rp-panel--open');
}

function _reClosePanel(inst) {
  if (inst.panel) {
    inst.panel.classList.remove('vm-rp-panel--open');
    inst.panel.innerHTML = _rePanelIdle();
  }
  if (inst.drawn && inst.map) {
    inst.map.removeLayer(inst.drawn);
    inst.drawn = null;
  }
  inst.history = [];
  inst.ctx     = null;
}

function _rePanelSetContent(inst, html) {
  if (inst.panel) inst.panel.innerHTML = html;
}

// ── Toast ─────────────────────────────────────────────
function _reToast(inst, msg) {
  const mapEl = inst.map.getContainer();
  const old = mapEl.querySelector('.vm-rp-toast');
  if (old) old.remove();
  const t = document.createElement('div');
  t.className   = 'vm-rp-toast';
  t.textContent = msg;
  mapEl.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

function _reEsc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
