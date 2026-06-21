/* ══════════════════════════════════════════════════════
   Layer 2 — Gemini Answer Framer
   Model: gemini-2.0-flash  (15 RPM / 1500 RPD free)
   • 20-second AbortSignal timeout
   • 15-minute in-memory response cache
   • Auto-retry with backoff on 429 (up to 3 retries)
   NOTE: GEMINI_KEY must start with "AIza..." not "AQ."
══════════════════════════════════════════════════════ */

function _geminiUrl() {
  return `${AI_CONFIG.gemini.baseEndpoint}/${AI_CONFIG.gemini.model}:generateContent?key=${GEMINI_KEY}`;
}

// 15-minute in-memory cache — avoids repeat Gemini calls for identical prompts
const _gemCache = new Map();
const _GEM_TTL  = 15 * 60 * 1000;

function _gemCacheKey(prompt) {
  return prompt.slice(0, 180);
}

async function callGemini(prompt, maxTokens) {
  // Cache check — same prompt within 15 min → instant return
  const ck  = _gemCacheKey(prompt);
  const hit = _gemCache.get(ck);
  if (hit && Date.now() - hit.ts < _GEM_TTL) return hit.text;

  // Up to 3 attempts with exponential backoff on 429
  for (let attempt = 0; attempt < 4; attempt++) {
    if (attempt > 0) {
      const delay = attempt * 4000; // 4s, 8s, 12s
      console.log(`[Gemini] Retrying in ${delay / 1000}s (attempt ${attempt + 1}/4)`);
      await new Promise(r => setTimeout(r, delay));
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);

    try {
      const res = await fetch(_geminiUrl(), {
        method:  'POST',
        signal:  controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: {
            maxOutputTokens: maxTokens || AI_CONFIG.gemini.maxTokens,
            temperature:     0.6,
          },
          safetySettings: [
            { category: 'HARM_CATEGORY_HARASSMENT',        threshold: 'BLOCK_NONE' },
            { category: 'HARM_CATEGORY_HATE_SPEECH',       threshold: 'BLOCK_NONE' },
            { category: 'HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold: 'BLOCK_NONE' },
            { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_NONE' },
          ],
        }),
      });

      if (res.status === 429) {
        clearTimeout(timer);
        if (attempt < 3) continue; // retry up to 3 times
        return '⏳ Gemini is busy — please wait 30 seconds and try again.';
      }

      if (res.status === 400 || res.status === 401 || res.status === 403) {
        const body = await res.text().catch(() => '');
        clearTimeout(timer);
        console.error('[Gemini] Auth/Key error', res.status, body.slice(0, 200));
        return `Gemini key error (${res.status}) — check GEMINI_KEY in .env.`;
      }

      if (!res.ok) {
        const body = await res.text().catch(() => '');
        console.warn('[Gemini] HTTP', res.status, body.slice(0, 200));
        clearTimeout(timer);
        if (attempt < 3) continue;
        return `⚠️ AI error (${res.status}) — try again.`;
      }

      const data = await res.json();
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (!text) {
        clearTimeout(timer);
        return 'No explanation generated — try again.';
      }

      const result = text.trim();
      _gemCache.set(ck, { ts: Date.now(), text: result });
      clearTimeout(timer);
      return result;

    } catch (err) {
      clearTimeout(timer);
      if (err.name === 'AbortError') return '⏱️ AI response timed out — please try again.';
      if (attempt < 3) continue; // retry on network error too
      console.warn('[Gemini] error:', err.message);
      return '🔌 AI insight temporarily unavailable — check your internet connection.';
    }
  }
}
