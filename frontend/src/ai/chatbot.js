/* ══════════════════════════════════════════════════════
   Feature 2 — Global Sticky Chatbot
   Single instance, persists across all pages.
   Memory: localStorage, last 12 turns (24 messages).
   Two-layer pipeline: Groq routes → Gemini answers.
══════════════════════════════════════════════════════ */

const _CHAT_KEY     = 'violationmap_chat_history';
const _CHAT_TURNS   = 12; // pairs

let _chatOpen    = false;
let _chatSending = false;
let _sendTimer   = null;

// ── Entry point (called once from index.html) ────────
function initChatbot() {
  const root = document.createElement('div');
  root.id = 'vm-chatbot-root';
  root.innerHTML = _chatHTML();
  document.body.appendChild(root);

  _chatLoadHistory();

  document.getElementById('vm-chat-toggle').addEventListener('click', _chatToggle);
  document.getElementById('vm-chat-close' ).addEventListener('click', _chatClose);
  document.getElementById('vm-chat-clear' ).addEventListener('click', _chatClear);
  document.getElementById('vm-chat-send'  ).addEventListener('click', _chatSend);

  document.getElementById('vm-chat-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _chatSend(); }
  });

  document.querySelectorAll('.vm-chat-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.getElementById('vm-chat-input').value = chip.dataset.q;
      _chatSend();
    });
  });

  // Show notification dot if there is saved history
  if (_chatGetHistory().length > 0) {
    document.getElementById('vm-chat-notif').style.display = 'block';
  }
}

function _chatHTML() {
  return `
    <button id="vm-chat-toggle" class="vm-chat-toggle" aria-label="Open AI assistant">
      <span class="vm-chat-toggle-icon">🤖</span>
      <span id="vm-chat-notif" class="vm-chat-notif" style="display:none"></span>
    </button>

    <div id="vm-chat-panel" class="vm-chat-panel" aria-hidden="true">
      <div class="vm-chat-header">
        <div class="vm-chat-header-info">
          <span class="vm-chat-title">🤖 ViolationMap AI</span>
          <span class="vm-chat-subtitle">Groq × Gemini</span>
        </div>
        <div class="vm-chat-header-actions">
          <button id="vm-chat-clear" class="vm-chat-icon-btn" title="Clear history">🗑</button>
          <button id="vm-chat-close" class="vm-chat-icon-btn" title="Close">✕</button>
        </div>
      </div>

      <div id="vm-chat-messages" class="vm-chat-messages"></div>

      <div class="vm-chat-chips">
        <button class="vm-chat-chip" data-q="Top hotspot right now?">Top hotspot right now?</button>
        <button class="vm-chat-chip" data-q="Peak violation hour?">Peak violation hour?</button>
        <button class="vm-chat-chip" data-q="Which area needs enforcement?">Which area needs enforcement?</button>
      </div>

      <div class="vm-chat-input-row">
        <input id="vm-chat-input" class="vm-chat-input" type="text"
               placeholder="Ask about Bengaluru traffic…" maxlength="300" autocomplete="off" />
        <button id="vm-chat-send" class="vm-chat-send-btn" aria-label="Send">➤</button>
      </div>
    </div>`;
}

// ── Panel open / close ───────────────────────────────
function _chatToggle() { _chatOpen ? _chatClose() : _chatOpen2(); }

function _chatOpen2() {
  _chatOpen = true;
  const panel = document.getElementById('vm-chat-panel');
  panel.classList.add('vm-chat-panel-open');
  panel.setAttribute('aria-hidden', 'false');
  document.getElementById('vm-chat-notif').style.display = 'none';
  const msgs = document.getElementById('vm-chat-messages');
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
}

function _chatClose() {
  _chatOpen = false;
  const panel = document.getElementById('vm-chat-panel');
  panel.classList.remove('vm-chat-panel-open');
  panel.setAttribute('aria-hidden', 'true');
}

function _chatClear() {
  localStorage.removeItem(_CHAT_KEY);
  const msgs = document.getElementById('vm-chat-messages');
  if (msgs) msgs.innerHTML = '';
}

// ── History persistence ──────────────────────────────
function _chatGetHistory() {
  try { return JSON.parse(localStorage.getItem(_CHAT_KEY) || '[]'); }
  catch { return []; }
}

function _chatSaveHistory(history) {
  const trimmed = history.slice(-_CHAT_TURNS * 2);
  localStorage.setItem(_CHAT_KEY, JSON.stringify(trimmed));
}

function _chatLoadHistory() {
  const history = _chatGetHistory();
  const msgs = document.getElementById('vm-chat-messages');
  if (!msgs) return;
  history.forEach(m => msgs.appendChild(_chatMsgEl(m.role, m.content, m.time)));
  msgs.scrollTop = msgs.scrollHeight;
}

// ── DOM helpers ──────────────────────────────────────
function _chatMsgEl(role, content, time) {
  const div = document.createElement('div');
  div.className = `vm-msg vm-msg-${role}`;
  div.innerHTML = `
    <div class="vm-msg-bubble">${_chatEsc(content)}</div>
    <div class="vm-msg-time">${time || _chatTime()}</div>`;
  return div;
}

function _chatTime() {
  return new Date().toLocaleTimeString('en-IN',
    { hour: '2-digit', minute: '2-digit', hour12: false });
}

function _chatEsc(str) {
  return String(str || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\n/g, '<br>');
}

function _chatPage() {
  const h = window.location.hash || '#/';
  if (h.includes('past-data'))        return 'Past Data (Historical Violations)';
  if (h.includes('only-prediction'))  return 'Predictive Heatmap';
  if (h.includes('traffic-severity')) return 'Severity Heatmap';
  return 'Home';
}

function _chatTop5(data) {
  if (!Array.isArray(data) || !data.length) return [];
  const key = ['lightgbm_prediction', 'baseline_prediction', 'naive_prediction']
    .find(k => data[0][k] !== undefined);
  if (!key) return [];
  return [...data]
    .sort((a, b) => (b[key] || 0) - (a[key] || 0))
    .slice(0, 5)
    .map(d => ({ name: d.location_key || 'Unknown', score: (d[key] || 0).toFixed(3) }));
}

// ── Send message ─────────────────────────────────────
function _chatSend() {
  // Debounce double-clicks
  if (_sendTimer) { clearTimeout(_sendTimer); _sendTimer = null; }
  _sendTimer = setTimeout(_chatDoSend, 80);
}

async function _chatDoSend() {
  if (_chatSending) return;
  const input = document.getElementById('vm-chat-input');
  const question = input.value.trim();
  if (!question) return;

  _chatSending = true;
  input.value  = '';

  const msgs = document.getElementById('vm-chat-messages');
  const t1   = _chatTime();

  // User bubble
  msgs.appendChild(_chatMsgEl('user', question, t1));
  msgs.scrollTop = msgs.scrollHeight;

  // Typing indicator
  const typingEl = document.createElement('div');
  typingEl.className = 'vm-msg vm-msg-ai';
  typingEl.innerHTML = '<div class="vm-msg-bubble vm-typing-indicator"><span></span><span></span><span></span></div>';
  msgs.appendChild(typingEl);
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const history  = _chatGetHistory().slice(-8); // last 4 turns for context
    const histText = history.map(m => `${m.role}: ${m.content}`).join('\n');
    const page     = _chatPage();
    const predTop5 = _chatTop5(window.lastPredictionData);
    const sevTop5  = _chatTop5(window.lastSeverityData);
    const activeTop5 = predTop5.length ? predTop5 : sevTop5;
    const top5Text = activeTop5.map((h, i) => `${i+1}. ${h.name} (${h.score})`).join('; ');

    // Shared prompt for the answer layer
    const answerSystem = `You are a Bengaluru traffic analyst AI assistant embedded in a live traffic dashboard called ViolationMap. Answer in 1-2 sentences max (under 60 words). Be specific and name junctions when available. Current page: ${page}. Top hotspots: ${top5Text || 'none loaded'}.`;
    const answerUser   = histText
      ? `Conversation so far:\n${histText.slice(-400)}\n\nNew question: ${question}`
      : question;

    const answer = await callGroqChat(answerSystem, answerUser);

    msgs.removeChild(typingEl);
    const t2 = _chatTime();
    msgs.appendChild(_chatMsgEl('ai', answer, t2));
    msgs.scrollTop = msgs.scrollHeight;

    const history2 = _chatGetHistory();
    history2.push({ role: 'user', content: question, time: t1 });
    history2.push({ role: 'ai',   content: answer,   time: t2 });
    _chatSaveHistory(history2);

  } catch {
    msgs.removeChild(typingEl);
    msgs.appendChild(_chatMsgEl('ai', 'Sorry, something went wrong. Please try again.', _chatTime()));
    msgs.scrollTop = msgs.scrollHeight;
  } finally {
    _chatSending = false;
  }
}
