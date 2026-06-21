/* ── AI Configuration ─────────────────────────────── */
const AI_CONFIG = {
  groq: {
    // llama3-70b-versatile was deprecated; new name has dashes
    model:    'llama-3.3-70b-versatile',
    endpoint: 'https://api.groq.com/openai/v1/chat/completions',
    timeout:  5000,
  },
  gemini: {
    // gemini-2.0-flash: 15 RPM / 1500 RPD free — more reliable than flash-lite
    model:        'gemini-2.0-flash',
    baseEndpoint: 'https://generativelanguage.googleapis.com/v1beta/models',
    maxTokens:    100,   // default; each call can override
  },
  pages: {
    'past-data':  { accent: '#ef4444', label: 'Past Violation Data',   barId: 'ai-bar-past-data'  },
    'prediction': { accent: '#6366f1', label: 'Predictive Heatmap',    barId: 'ai-bar-prediction'  },
    'severity':   { accent: '#f59e0b', label: 'Severity Heatmap',      barId: 'ai-bar-severity'    },
  },
};
