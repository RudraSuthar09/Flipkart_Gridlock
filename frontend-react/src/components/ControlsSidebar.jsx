import React, { useState, useEffect } from 'react';
import { Play, Loader2, Moon, Sun, TrendingUp } from 'lucide-react';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { scoreKey, riskColor, sevRiskColor } from '../utils/colorUtils';
import './ControlsSidebar.css';

const MODEL_OPTIONS = [
  { id: 'lightgbm', label: 'LightGBM' },
  { id: 'baseline', label: 'Baseline' },
  { id: 'naive',    label: 'Naive' },
];

const NIGHT_HOURS = new Set([22, 23, 0, 1, 2, 3, 4, 5]);

const ControlsSidebar = ({
  title, subtitle, icon, statusColor, statusLabel,
  timestamp, onTimestampChange,
  selectedModel, onModelChange,
  onRun, loading, error,
  predictions, scoreColor, legend, extraContent, displayTopN,
  stationOptions = [],
  selectedStation = '',
  onStationChange,
  showForecast = false,
  onForecastToggle,
}) => {
  const key    = scoreKey(selectedModel);
  const colorFn = scoreColor === 'amber' ? sevRiskColor : riskColor;

  const [nightMode, setNightMode]         = useState(false);
  const [hourlyData, setHourlyData]       = useState([]);
  const [hourlyLoading, setHourlyLoading] = useState(false);

  const scores       = predictions.map(p => p[key] || 0);
  const maxScore     = scores.length ? Math.max(...scores) : 0;
  const effectiveMax = Math.max(maxScore, 1e-6);

  const top20 = [...predictions]
    .sort((a, b) => (b[key] || 0) - (a[key] || 0))
    .slice(0, 20);

  const topLocationKey = top20[0]?.location_key;

  // Fetch hourly profile when night mode is toggled on or top location changes
  useEffect(() => {
    if (!nightMode || !topLocationKey) return;
    setHourlyLoading(true);
    axios.get(`/api/v1/hourly-profile?location_key=${encodeURIComponent(topLocationKey)}`, { timeout: 10000 })
      .then(r => setHourlyData(r.data || []))
      .catch(() => setHourlyData([]))
      .finally(() => setHourlyLoading(false));
  }, [nightMode, topLocationKey]);

  // Set timestamp to nearest night hour when night mode activates
  const handleNightModeToggle = () => {
    const next = !nightMode;
    setNightMode(next);
    if (next) {
      const now = new Date();
      const nightHour = 3; // 3 AM peak
      const d = new Date(now);
      d.setHours(nightHour, 0, 0, 0);
      const pad = n => String(n).padStart(2, '0');
      const val = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
      onTimestampChange(val);
    }
  };

  const hourlyMax = hourlyData.length ? Math.max(...hourlyData.map(d => d.mean_violations), 1e-6) : 1;

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

      {/* ── Scrollable middle body ────────────────────────── */}
      <div className="cs-scroll-body">

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

        {/* Police Station Filter */}
        {stationOptions.length > 0 && (
          <section className="cs-section">
            <div className="cs-section-header">
              <span className="cs-section-icon">🚔</span>
              <h3>Police Station</h3>
            </div>
            <select
              className="cs-station-select"
              value={selectedStation}
              onChange={e => onStationChange(e.target.value)}
            >
              <option value="">All stations ({stationOptions.length})</option>
              {stationOptions.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </section>
        )}

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

        {/* Night Mode Toggle */}
        <div className="cs-night-row">
          <span className="cs-night-label">
            {nightMode ? <Moon size={14} /> : <Sun size={14} />}
            Night Mode
            <span className="cs-night-hint">66% of violations 10pm–6am</span>
          </span>
          <button
            className={`cs-night-toggle ${nightMode ? 'active' : ''}`}
            onClick={handleNightModeToggle}
            title="Show peak violation hours"
          >
            <span className="cs-night-thumb" />
          </button>
        </div>

        {/* Night Mode Chart */}
        {nightMode && (
          <section className="cs-section cs-night-chart-section">
            <div className="cs-section-header">
              <TrendingUp size={14} />
              <h3>24h Violation Distribution</h3>
            </div>
            {topLocationKey && (
              <p className="cs-chart-loc">{topLocationKey.replace(/^[A-Z0-9]+ - /, '')}</p>
            )}
            {hourlyLoading ? (
              <div className="cs-chart-loading"><Loader2 size={14} className="spin-icon" /> Loading…</div>
            ) : hourlyData.length > 0 ? (
              <ResponsiveContainer width="100%" height={130}>
                <BarChart data={hourlyData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: 9 }}
                    tickFormatter={h => `${h}h`}
                    interval={3}
                  />
                  <YAxis tick={{ fontSize: 9 }} />
                  <Tooltip
                    formatter={(v) => [v.toFixed(2), 'Avg violations']}
                    labelFormatter={h => `Hour ${h}:00`}
                  />
                  <Bar dataKey="mean_violations" radius={[2, 2, 0, 0]}>
                    {hourlyData.map(entry => (
                      <Cell
                        key={entry.hour}
                        fill={NIGHT_HOURS.has(entry.hour) ? '#6366f1' : '#94a3b8'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="cs-empty">Run a prediction first</p>
            )}
            <p className="cs-night-note">Purple = night hours (10pm–6am)</p>
          </section>
        )}

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
                const pct   = effectiveMax > 0 ? ((score / effectiveMax) * 100).toFixed(0) : 0;
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

        {error && <div className="cs-error" style={{ margin: '8px 20px 0' }}>⚠ {error}</div>}

      </div>{/* /cs-scroll-body */}

      {/* Run Button — fixed outside scroll */}
      <button className="cs-run-btn" onClick={onRun} disabled={loading}>
        {loading ? <Loader2 size={16} className="spin-icon" /> : <Play size={16} />}
        {loading ? 'Running…' : 'Run Prediction'}
      </button>

      {/* Forecast Toggle Button */}
      {onForecastToggle && (
        <button
          className={`cs-forecast-btn ${showForecast ? 'active' : ''}`}
          onClick={onForecastToggle}
        >
          📈 {showForecast ? 'Hide 24h Forecast' : '24h Forecast'}
        </button>
      )}

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
