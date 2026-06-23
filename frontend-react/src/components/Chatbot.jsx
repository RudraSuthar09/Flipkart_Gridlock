import React, { useState, useRef, useEffect, useCallback } from 'react';
import { MessageCircle, X, Trash2, Send } from 'lucide-react';
import './Chatbot.css';

const GROQ_KEY    = import.meta.env.VITE_GROQ_API_KEY || '';
const GROQ_URL    = 'https://api.groq.com/openai/v1/chat/completions';
const GROQ_MODEL  = 'llama-3.3-70b-versatile';
const CHAT_KEY    = 'urbanintel_chat_history';
const MAX_TURNS   = 12;

const QUICK_CHIPS = [
  'Top hotspot right now?',
  'Peak violation hour?',
  'Which area needs enforcement?',
];

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(CHAT_KEY) || '[]'); } catch { return []; }
}

function saveHistory(h) {
  localStorage.setItem(CHAT_KEY, JSON.stringify(h.slice(-(MAX_TURNS * 2))));
}

function nowTime() {
  return new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
}

async function callGroq(systemPrompt, userMessage) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 12000);
  try {
    const res = await fetch(GROQ_URL, {
      method: 'POST',
      signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${GROQ_KEY}` },
      body: JSON.stringify({
        model: GROQ_MODEL,
        messages: [{ role: 'system', content: systemPrompt }, { role: 'user', content: userMessage }],
        temperature: 0.65,
        max_tokens: 250,
      }),
    });
    if (!res.ok) throw new Error(`Groq HTTP ${res.status}`);
    const data = await res.json();
    return data.choices?.[0]?.message?.content?.trim() || 'No response.';
  } finally {
    clearTimeout(timer);
  }
}

const Chatbot = ({ predictions, activePage }) => {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(loadHistory);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  const top5Text = useCallback(() => {
    if (!predictions || !predictions.length) return 'none loaded';
    const key = 'lightgbm_prediction';
    return [...predictions]
      .sort((a, b) => (b[key] || 0) - (a[key] || 0))
      .slice(0, 5)
      .map((d, i) => `${i + 1}. ${d.location_key} (${(d[key] || 0).toFixed(3)})`)
      .join('; ');
  }, [predictions]);

  const sendMessage = useCallback(async (text) => {
    const question = (text || input).trim();
    if (!question || sending) return;
    setSending(true);
    setInput('');

    const t1 = nowTime();
    const userMsg = { role: 'user', content: question, time: t1 };
    const newMsgs = [...messages, userMsg];
    setMessages(newMsgs);

    try {
      const histCtx = newMsgs.slice(-8).map(m => `${m.role}: ${m.content}`).join('\n');
      const page = activePage === 'prediction' ? 'Count Heatmap' : 'Severity Heatmap';
      const system = `You are a Bengaluru traffic analyst AI embedded in the Sugama Sanchara Bengaluru dashboard. Answer in 1-2 sentences max (under 60 words). Be specific, name junctions when possible. Current page: ${page}. Top hotspots: ${top5Text()}.`;
      const userQ = histCtx.length > 50
        ? `Conversation so far:\n${histCtx.slice(-400)}\n\nNew question: ${question}`
        : question;

      const answer = await callGroq(system, userQ);
      const t2 = nowTime();
      const aiMsg = { role: 'ai', content: answer, time: t2 };
      const final = [...newMsgs, aiMsg];
      setMessages(final);
      saveHistory(final);
    } catch (err) {
      const errMsg = { role: 'ai', content: 'Sorry, something went wrong. Please try again.', time: nowTime() };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setSending(false);
    }
  }, [input, messages, sending, top5Text, activePage]);

  const clearHistory = () => {
    localStorage.removeItem(CHAT_KEY);
    setMessages([]);
  };

  const hasHistory = messages.length > 0;

  return (
    <>
      {/* Floating toggle button */}
      <button
        className={`chatbot-toggle ${hasHistory && !open ? 'has-notif' : ''}`}
        onClick={() => setOpen(o => !o)}
        aria-label="Open AI assistant"
      >
        {open ? <X size={24} /> : <MessageCircle size={24} />}
        {hasHistory && !open && <span className="chat-notif-dot" />}
      </button>

      {/* Chat panel */}
      <div className={`chatbot-panel ${open ? 'chatbot-panel-open' : ''}`}>
        {/* Header */}
        <div className="chat-header">
          <div className="chat-header-info">
            <span className="chat-title">🤖 Sugama Sanchara AI</span>
            <span className="chat-subtitle">Groq · Llama 3.3 70B</span>
          </div>
          <div className="chat-header-actions">
            <button className="chat-icon-btn" onClick={clearHistory} title="Clear history"><Trash2 size={14} /></button>
            <button className="chat-icon-btn" onClick={() => setOpen(false)} title="Close"><X size={14} /></button>
          </div>
        </div>

        {/* Messages */}
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-welcome">
              <div className="chat-welcome-icon">🤖</div>
              <p>Ask me about Bengaluru traffic hotspots, enforcement priorities, or prediction insights.</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
              <div className="chat-bubble">{msg.content}</div>
              <div className="chat-time">{msg.time}</div>
            </div>
          ))}
          {sending && (
            <div className="chat-msg chat-msg-ai">
              <div className="chat-bubble chat-typing">
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick chips */}
        <div className="chat-chips">
          {QUICK_CHIPS.map(q => (
            <button key={q} className="chat-chip" onClick={() => sendMessage(q)}>{q}</button>
          ))}
        </div>

        {/* Input */}
        <div className="chat-input-row">
          <input
            className="chat-input"
            type="text"
            placeholder="Ask about Bengaluru traffic…"
            value={input}
            maxLength={300}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          />
          <button className="chat-send-btn" onClick={() => sendMessage()} disabled={sending || !input.trim()}>
            <Send size={16} />
          </button>
        </div>
      </div>
    </>
  );
};

export default Chatbot;
