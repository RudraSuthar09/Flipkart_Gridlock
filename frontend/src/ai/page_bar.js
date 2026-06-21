/* ══════════════════════════════════════════════════════
   Feature 1 — Per-Page AI Explanation Bar
   Shows on: Past Data, Predictive Heatmap, Severity pages.

   Quota strategy:
   • Uses GROQ ONLY (no Gemini) — Groq free tier is much
     more generous (no daily limit, 200 RPM).
   • Caches by data-hash: same top-3 hotspots → no API call.
   • Manual refresh button to override the cache.
══════════════════════════════════════════════════════ */

const _barCache = new Map(); // "pageKey:dataHash" → insight text

function updatePageBar(pageKey, data) {
  const config = AI_CONFIG.pages[pageKey];
  if (!config) return;
  const bar = document.getElementById(config.barId);
  if (!bar) return;

  bar._aiPageKey  = pageKey;
  bar._aiLastData = data;

  const cacheKey = `${pageKey}:${_barDataHash(data)}`;
  const cached   = _barCache.get(cacheKey);
  if (cached) {
    _barShowText(bar, cached, config.accent);
    return;
  }

  _barShowSkeleton(bar, config.accent);
  _barFetchInsight(pageKey, data, config)
    .then(text => {
      _barCache.set(cacheKey, text);
      _barShowText(bar, text, config.accent);
    })
    .catch(() => _barShowText(bar, 'AI insight unavailable.', config.accent));
}

// ── Simple hash: top-3 location keys + page ──────────
function _barDataHash(data) {
  if (!Array.isArray(data) || !data.length) return 'empty';
  const key = ['lightgbm_prediction', 'baseline_prediction', 'naive_prediction', 'score']
    .find(k => data[0][k] !== undefined);
  if (!key) return 'nokey';
  return [...data]
    .sort((a, b) => (b[key] || 0) - (a[key] || 0))
    .slice(0, 3)
    .map(d => d.location_key || '?')
    .join(',');
}

// ── Skeleton ──────────────────────────────────────────
function _barShowSkeleton(bar, accent) {
  bar.classList.remove('ai-bar-visible');
  bar.innerHTML = `
    <div class="ai-bar-inner">
      <div class="ai-bar-left">
        <span class="ai-bar-icon">🤖</span>
        <span class="ai-bar-label">AI Insight</span>
      </div>
      <div class="ai-bar-center">
        <div class="ai-shimmer"></div>
        <div class="ai-shimmer ai-shimmer-short"></div>
      </div>
      <div class="ai-bar-right">
        <button class="ai-bar-refresh" disabled>↻</button>
      </div>
    </div>`;
  bar.style.setProperty('--bar-accent', accent);
  void bar.offsetHeight;
  bar.classList.add('ai-bar-visible');
}

// ── Text ──────────────────────────────────────────────
function _barShowText(bar, text, accent) {
  bar.classList.remove('ai-bar-visible');
  bar.innerHTML = `
    <div class="ai-bar-inner">
      <div class="ai-bar-left">
        <span class="ai-bar-icon">🤖</span>
        <span class="ai-bar-label">AI Insight</span>
      </div>
      <div class="ai-bar-center">
        <span class="ai-bar-explanation">${_barEsc(text)}</span>
      </div>
      <div class="ai-bar-right">
        <button class="ai-bar-refresh" title="Refresh AI insight">↻</button>
      </div>
    </div>`;
  bar.style.setProperty('--bar-accent', accent);
  void bar.offsetHeight;
  bar.classList.add('ai-bar-visible');
}

function _barEsc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Groq-only fetch (no Gemini — saves quota) ────────
async function _barFetchInsight(pageKey, data, config) {
  const top5 = _barTop5(data);
  const top5Text = top5.length
    ? top5.map((h, i) => `${i + 1}. ${h.name} (${h.score})`).join('; ')
    : 'no prediction data loaded';

  // Single Groq call — fast + free quota
  const system = `You are a Bengaluru traffic analyst. Write ONE concise sentence (max 60 words) as a banner insight for a traffic dashboard. Mention 1-2 specific junction names if data is available. Be direct, no filler phrases, no markdown.`;
  const user   = `Page: ${config.label}. Top hotspots: ${top5Text}.`;

  const res = await fetch(AI_CONFIG.groq.endpoint, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${GROQ_KEY}` },
    body: JSON.stringify({
      model:       AI_CONFIG.groq.model,
      messages:    [{ role: 'system', content: system }, { role: 'user', content: user }],
      temperature: 0.4,
      max_tokens:  90,
    }),
  });

  if (!res.ok) {
    const err = await res.text().catch(() => '');
    throw new Error(`Groq ${res.status}: ${err.slice(0, 100)}`);
  }
  const data2 = await res.json();
  return (data2.choices?.[0]?.message?.content || '').trim() || 'No insight generated.';
}

function _barTop5(data) {
  if (!Array.isArray(data) || !data.length) return [];
  const key = ['lightgbm_prediction', 'baseline_prediction', 'naive_prediction', 'score']
    .find(k => data[0][k] !== undefined);
  if (!key) return [];
  return [...data]
    .sort((a, b) => (b[key] || 0) - (a[key] || 0))
    .slice(0, 5)
    .map(d => ({ name: d.location_key || 'Unknown', score: (d[key] || 0).toFixed(3) }));
}

// ── Refresh button — bypasses cache ──────────────────
document.addEventListener('click', function (e) {
  if (!e.target.classList.contains('ai-bar-refresh') || e.target.disabled) return;
  const bar = e.target.closest('.ai-page-bar');
  if (!bar || !bar._aiPageKey) return;

  // Clear cache entry so refresh gets fresh data
  const cacheKey = `${bar._aiPageKey}:${_barDataHash(bar._aiLastData)}`;
  _barCache.delete(cacheKey);
  updatePageBar(bar._aiPageKey, bar._aiLastData);
});
