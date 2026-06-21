import React from 'react';
import { Play, Loader2 } from 'lucide-react';
import { scoreKey, riskColor, sevRiskColor } from '../utils/colorUtils';
import './ControlsSidebar.css';

const MODEL_OPTIONS = [
  { id: 'lightgbm', label: 'LightGBM' },
  { id: 'baseline', label: 'Baseline' },
  { id: 'naive',    label: 'Naive' },
];

const ControlsSidebar = ({
  title, subtitle, icon, statusColor, statusLabel,
  timestamp, onTimestampChange,
  selectedModel, onModelChange,
  onRun, loading, error,
  predictions, scoreColor, legend, extraContent, displayTopN,
}) => {
  const key = scoreKey(selectedModel);
  const colorFn = scoreColor === 'amber' ? sevRiskColor : riskColor;

  const scores = predictions.map(p => p[key] || 0);
  const maxScore = scores.length ? Math.max(...scores) : 0;
  const effectiveMax = Math.max(maxScore, 1e-6);

  const top20 = [...predictions]
    .sort((a, b) => (b[key] || 0) - (a[key] || 0))
    .slice(0, 20);

  return (
    <aside className="controls-sidebar">
      {/* Brand */}
      <div className="cs-brand">
        <div className={`cs-brand-icon ${icon}`}>
          {icon === 'severity' ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          )}
        </div>
        <div>
          <h2 className="cs-title">{title}</h2>
          <p className="cs-subtitle">{subtitle}</p>
        </div>
      </div>

      {/* API Status */}
      <div className="cs-api-status">
        <span className="cs-api-dot" style={{ backgroundColor: statusColor }} />
        <span className="cs-api-label">{statusLabel}</span>
      </div>

      {/* Extra content (e.g. confidence banner) */}
      {extraContent}

      {/* Time Picker */}
      <section className="cs-section">
        <div className="cs-section-header">
          <span className="cs-section-icon">🕐</span>
          <h3>Target Time</h3>
        </div>
        <label className="cs-label">
          Date &amp; Hour
          <input
            type="datetime-local"
            className="cs-datetime-input"
            value={timestamp}
            onChange={e => onTimestampChange(e.target.value)}
          />
        </label>
      </section>

      {/* Model Toggle */}
      <section className="cs-section">
        <div className="cs-section-header">
          <span className="cs-section-icon">🤖</span>
          <h3>Model</h3>
        </div>
        <div className="cs-model-row">
          {MODEL_OPTIONS.map(m => (
            <button
              key={m.id}
              className={`cs-model-btn ${selectedModel === m.id ? 'active' : ''}`}
              onClick={() => onModelChange(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </section>

      {/* Run Button */}
      <button className="cs-run-btn" onClick={onRun} disabled={loading}>
        {loading ? <Loader2 size={16} className="spin-icon" /> : <Play size={16} />}
        {loading ? 'Running…' : 'Run Prediction'}
      </button>

      {error && <div className="cs-error">⚠ {error}</div>}

      {/* Legend */}
      <section className="cs-section">
        <span className="cs-chip-label">Risk Level</span>
        <div className="cs-legend-bar-wrap">
          <span className="cs-legend-lo">{legend.lo}</span>
          <div className="cs-legend-bar" style={{ background: legend.gradient }} />
          <span className="cs-legend-hi">{legend.hi}</span>
        </div>
      </section>

      {/* Top 20 Hotspots */}
      <section className="cs-section cs-top-section">
        <div className="cs-section-header">
          <span className="cs-section-icon">🚨</span>
          <h3>Top 20 Hotspots</h3>
        </div>
        {top20.length === 0 ? (
          <p className="cs-empty">Run a prediction to see hotspots</p>
        ) : (
          <ul className="cs-top-list">
            {top20.map((loc, i) => {
              const score = loc[key] || 0;
              const pct = effectiveMax > 0 ? ((score / effectiveMax) * 100).toFixed(0) : 0;
              const color = colorFn(score / effectiveMax);
              return (
                <li key={loc.location_key} className="cs-top-item">
                  <div className="cs-top-rank" style={{ background: color }}>{i + 1}</div>
                  <div className="cs-top-info">
                    <div className="cs-top-name">
                      {loc.location_key.replace(/^[A-Z0-9]+ - /, '')}
                    </div>
                    <div className="cs-top-meta">
                      {loc.area || ''}{loc.area && loc.police_station ? ' · ' : ''}{loc.police_station || ''}
                    </div>
                  </div>
                  <div className="cs-top-score-wrap">
                    <div className="cs-top-score">{score.toFixed(2)}</div>
                    <div className="cs-top-bar-track">
                      <div className="cs-top-bar-fill" style={{ width: `${pct}%`, background: color }} />
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Stats */}
      <div className="cs-stats">
        <div className="cs-stat-item">
          <span>Total Locs</span>
          <strong>{predictions.length ? predictions.length.toLocaleString() : '—'}</strong>
        </div>
        <div className="cs-stat-item">
          <span>Displayed</span>
          <strong>{predictions.length ? predictions.length.toLocaleString() : '—'}</strong>
        </div>
        <div className="cs-stat-item">
          <span>Max Risk Score</span>
          <strong>{predictions.length ? maxScore.toFixed(2) : '—'}</strong>
        </div>
      </div>
    </aside>
  );
};

export default ControlsSidebar;
