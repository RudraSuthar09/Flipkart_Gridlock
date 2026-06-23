import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Loader2, Download } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid
} from 'recharts';
import './ReportsPage.css';

// Guards against null, undefined, AND NaN
const fmt     = n => (n == null || isNaN(Number(n))) ? '—' : Number(n).toLocaleString('en-IN');
const fmtPct  = n => (n == null || isNaN(Number(n))) ? '—' : `${Number(n).toFixed(1)}%`;
const fmtHour = h => h == null ? '—' : `${String(h).padStart(2, '0')}:00`;
const fmtJunction = s => s ? s.replace(/^[A-Z0-9]+ - /, '') : '—';

const COLORS = [
  '#6366f1','#f59e0b','#10b981','#ef4444','#3b82f6',
  '#8b5cf6','#f97316','#ec4899','#14b8a6','#84cc16',
  '#06b6d4','#a855f7','#fb923c','#e879f9','#4ade80',
];

const CHART_OPTS = [
  { key: 'total_violations', label: 'Total Violations' },
  { key: 'night_violations', label: 'Night Violations' },
  { key: 'unique_locations', label: 'Unique Locations' },
  { key: 'rejection_rate',   label: 'Rejection Rate'   },
];

let _statsCache = null;

export default function ReportsPage() {
  const [stats,    setStats]    = useState(_statsCache || []);
  const [loading,  setLoading]  = useState(!_statsCache);
  const [error,    setError]    = useState(null);
  const [sortKey,  setSortKey]  = useState('total_violations');
  const [sortDir,  setSortDir]  = useState('desc');
  const [chartKey, setChartKey] = useState('total_violations');

  useEffect(() => {
    if (_statsCache) return;
    axios.get('/api/v1/station-stats', { timeout: 15000 })
      .then(r => { _statsCache = r.data || []; setStats(_statsCache); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSort = key => {
    if (key === sortKey) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const sorted = [...stats].sort((a, b) => {
    const av = a[sortKey] ?? 0;
    const bv = b[sortKey] ?? 0;
    return sortDir === 'desc' ? bv - av : av - bv;
  });

  // Limit chart to top 15 by selected metric — 54 bars is unreadable
  const chartData = [...stats]
    .sort((a, b) => (b[chartKey] ?? 0) - (a[chartKey] ?? 0))
    .slice(0, 15)
    .map(s => ({
      name:  s.police_station || '—',
      value: chartKey === 'rejection_rate'
        ? parseFloat((s[chartKey] * 100).toFixed(1))
        : (s[chartKey] ?? 0),
    }));

  const totals = stats.reduce((acc, s) => ({
    violations: acc.violations + (s.total_violations || 0),
    locations:  acc.locations  + (s.unique_locations  || 0),
    night:      acc.night      + (s.night_violations  || 0),
  }), { violations: 0, locations: 0, night: 0 });

  const overallNightShare = totals.violations > 0
    ? (totals.night / totals.violations) * 100
    : null;

  const exportCSV = () => {
    const cols = [
      'police_station','total_violations','night_violations',
      'unique_locations','peak_hour','rejection_rate','top_location',
    ];
    const header = cols.join(',');
    const rows   = stats.map(s =>
      cols.map(c => {
        const v = s[c];
        return v == null ? '' : JSON.stringify(String(v));
      }).join(',')
    );
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' });
    const a    = document.createElement('a');
    a.href     = URL.createObjectURL(blob);
    a.download = `station_report_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const Th = ({ k, label }) => (
    <th
      className={`rp-th ${sortKey === k ? 'rp-th-active' : ''}`}
      onClick={() => handleSort(k)}
    >
      {label} {sortKey === k ? (sortDir === 'desc' ? '↓' : '↑') : ''}
    </th>
  );

  if (loading) return (
    <div className="rp-loading">
      <Loader2 size={28} className="spin-icon" />
      <p>Loading station reports…</p>
    </div>
  );

  if (error) return (
    <div className="rp-error">
      <p>⚠ Could not load station stats: {error}</p>
      <p>Ensure the API is running on port 8001.</p>
    </div>
  );

  return (
    <div className="rp-page">
      {/* Header */}
      <div className="rp-header">
        <div>
          <h1 className="rp-title">Station Performance Reports</h1>
          <p className="rp-sub">
            Violation breakdown across {stats.length} police station zones — 2,98,450 records · Nov 2023–Apr 2024.
          </p>
        </div>
        <button className="rp-export-btn" onClick={exportCSV}>
          <Download size={14} /> Export CSV
        </button>
      </div>

      {/* Summary cards */}
      <div className="rp-summary">
        <div className="rp-sum-card">
          <div className="rp-sum-val">{fmt(totals.violations)}</div>
          <div className="rp-sum-label">Total Violations</div>
          <div className="rp-sum-sub">across {stats.length} zones</div>
        </div>
        <div className="rp-sum-card">
          <div className="rp-sum-val">{fmt(totals.locations)}</div>
          <div className="rp-sum-label">Unique Locations</div>
          <div className="rp-sum-sub">distinct junctions</div>
        </div>
        <div className="rp-sum-card">
          <div className="rp-sum-val">{fmt(totals.night)}</div>
          <div className="rp-sum-label">Night Violations</div>
          <div className="rp-sum-sub">10 PM – 6 AM window</div>
        </div>
        <div className="rp-sum-card">
          <div className="rp-sum-val rp-sum-highlight">
            {fmtPct(overallNightShare)}
          </div>
          <div className="rp-sum-label">Night-time Share</div>
          <div className="rp-sum-sub">of all violations</div>
        </div>
      </div>

      {/* Chart — top 15 only */}
      <div className="rp-chart-card">
        <div className="rp-chart-header">
          <span className="rp-chart-title">
            Top 15 Stations —{' '}
            {CHART_OPTS.find(o => o.key === chartKey)?.label}
          </span>
          <div className="rp-chart-toggles">
            {CHART_OPTS.map(o => (
              <button
                key={o.key}
                className={`rp-chart-toggle ${chartKey === o.key ? 'active' : ''}`}
                onClick={() => setChartKey(o.key)}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10 }}
              angle={-35}
              textAnchor="end"
              interval={0}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={v =>
                chartKey === 'rejection_rate' ? `${v}%` : v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v
              }
            />
            <Tooltip
              formatter={(v) =>
                chartKey === 'rejection_rate'
                  ? [`${v}%`, 'Rejection Rate']
                  : [Number(v).toLocaleString('en-IN'), CHART_OPTS.find(o => o.key === chartKey)?.label]
              }
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={40}>
              {chartData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Table — all stations */}
      <div className="rp-table-card">
        <div className="rp-table-header">
          <span className="rp-table-title">All {stats.length} Stations</span>
          <span className="rp-table-hint">Click column headers to sort</span>
        </div>
        <div className="rp-table-scroll">
          <table className="rp-table">
            <thead>
              <tr>
                <th className="rp-th rp-th-fixed">#</th>
                <Th k="police_station"   label="Station" />
                <Th k="total_violations" label="Total" />
                <Th k="night_violations" label="Night" />
                <Th k="unique_locations" label="Locations" />
                <th className="rp-th">Night %</th>
                <Th k="rejection_rate"   label="Rejection Rate" />
                <th className="rp-th">Peak Hour</th>
                <th className="rp-th">Top Junction</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s, i) => {
                const nightShare = (s.total_violations && s.night_violations != null)
                  ? (s.night_violations / s.total_violations) * 100
                  : null;
                const nightCls = nightShare == null ? ''
                  : nightShare > 70 ? 'high'
                  : nightShare > 50 ? 'mid'
                  : 'low';
                const rejPct = s.rejection_rate != null ? s.rejection_rate * 100 : null;
                const rejCls = rejPct == null ? ''
                  : rejPct > 35 ? 'high'
                  : rejPct > 20 ? 'mid'
                  : 'low';

                return (
                  <tr key={s.police_station} className="rp-row">
                    <td className="rp-td rp-rank">
                      <span className="rp-rank-badge" style={{ background: COLORS[i % COLORS.length] }}>
                        {i + 1}
                      </span>
                    </td>
                    <td className="rp-td rp-station-name">{s.police_station || '—'}</td>
                    <td className="rp-td rp-num">{fmt(s.total_violations)}</td>
                    <td className="rp-td rp-num">{fmt(s.night_violations)}</td>
                    <td className="rp-td rp-num">{fmt(s.unique_locations)}</td>
                    <td className="rp-td rp-num">
                      {nightCls
                        ? <span className={`rp-pct-badge ${nightCls}`}>{fmtPct(nightShare)}</span>
                        : '—'}
                    </td>
                    <td className="rp-td rp-num">
                      {rejCls
                        ? <span className={`rp-pct-badge ${rejCls}`}>{fmtPct(rejPct)}</span>
                        : '—'}
                    </td>
                    <td className="rp-td rp-num">{fmtHour(s.peak_hour)}</td>
                    <td className="rp-td rp-top-loc" title={s.top_location || ''}>
                      {fmtJunction(s.top_location)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
