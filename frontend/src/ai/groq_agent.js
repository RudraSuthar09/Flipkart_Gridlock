/* ══════════════════════════════════════════════════════
   Layer 1 — Groq Agent
   Model: llama-3.3-70b-versatile
   callGroq()     → JSON routing only (for tool dispatch)
   callGroqChat() → Plain-text chatbot answers (primary AI)
   Timeout: 10 s
══════════════════════════════════════════════════════ */

async function callGroq(systemPrompt, userMessage) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), AI_CONFIG.groq.timeout);

  try {
    const res = await fetch(AI_CONFIG.groq.endpoint, {
      method: 'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${GROQ_KEY}`,
      },
      signal: controller.signal,
      body: JSON.stringify({
        model:           AI_CONFIG.groq.model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user',   content: userMessage  },
        ],
        temperature:     0.1,
        max_tokens:      220,
        response_format: { type: 'json_object' },
      }),
    });

    if (!res.ok) throw new Error(`Groq HTTP ${res.status}`);
    const data = await res.json();
    const raw  = data.choices?.[0]?.message?.content || '{}';
    return JSON.parse(raw);
  } catch (err) {
    if (err.name === 'AbortError') return { tool: 'fallback', error: 'timeout' };
    return { tool: 'fallback', error: err.message };
  } finally {
    clearTimeout(timer);
  }
}

// ── Plain-text chatbot answer (primary layer, no JSON constraint) ──
async function callGroqChat(systemPrompt, userMessage) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000); // 10 s timeout

  try {
    const res = await fetch(AI_CONFIG.groq.endpoint, {
      method: 'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${GROQ_KEY}`,
      },
      signal: controller.signal,
      body: JSON.stringify({
        model:       AI_CONFIG.groq.model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user',   content: userMessage  },
        ],
        temperature: 0.65,
        max_tokens:  250,
      }),
    });

    if (!res.ok) {
      const body = await res.text().catch(() => '');
      console.warn('[Groq Chat] HTTP', res.status, body.slice(0, 200));
      throw new Error(`Groq HTTP ${res.status}`);
    }

    const data = await res.json();
    const text = data.choices?.[0]?.message?.content || '';
    if (!text) throw new Error('Empty Groq response');
    return text.trim();

  } catch (err) {
    if (err.name === 'AbortError') throw new Error('timeout');
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
