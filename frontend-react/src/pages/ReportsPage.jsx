import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Loader2, Download } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid
} from 'recharts';
import './ReportsPage.css';

const fmt    = n => n == null ? '—' : Number(n).toLocaleString('en-IN');
const fmtPct = n => n == null ? '—' : `${Number(n).toFixed(1)}%`;

const COLORS = ['#6366f1','#f59e0b','#10b981','#ef4444','#3b82f6','#8b5cf6','#f97316','#ec4899'];

export default function ReportsPage() {
  const [stats,    setStats]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [sortKey,  setSortKey]  = useState('total_violations');
  const [sortDir,  setSortDir]  = useState('desc');
  const [chartKey, setChartKey] = useState('total_violations');

  useEffect(() => {
    axios.get('/api/v1/station-stats', { timeout: 15000 })
      .then(r => setStats(r.data || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSort = key => {
    if (key === sortKey) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const sorted = [...stats].sort((a, b) => {
    const av = a[sortKey] ?? 0, bv = b[sortKey] ?? 0;
    return sortDir === 'desc' ? bv - av : av - bv;
  });

  const chartData = [...stats]
    .sort((a, b) => (b[chartKey] ?? 0) - (a[chartKey] ?? 0))
    .map(s => ({ name: s.police_station?.replace(' Police Station', '') || s.police_station, value: s[chartKey] ?? 0 }));

  const totals = stats.reduce((acc, s) => ({
    violations: (acc.violations || 0) + (s.total_violations || 0),
    locations:  (acc.locations  || 0) + (s.unique_locations  || 0),
    night:      (acc.night      || 0) + (s.night_violations  || 0),
  }), {});

  const exportCSV = () => {
    const cols = ['police_station','total_violations','unique_locations','night_violations','peak_hour','top_location'];
    const rows = [cols.join(','), ...stats.map(s => cols.map(c => JSON.stringify(s[c] ?? '')).join(','))];
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `station_report_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  };

  const CHART_OPTS = [
    { key: 'total_violations', label: 'Total Violations' },
    { key: 'unique_locations', label: 'Unique Locations' },
    { key: 'night_violations', label: 'Night Violations' },
  ];

  const Th = ({ k, label }) => (
    <th className={`rp-th ${sortKey === k ? 'rp-th-active' : ''}`} onClick={() => handleSort(k)}>
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
          <p className="rp-sub">Violation breakdown by police station zone — sourced from 298,450 records.</p>
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
        </div>
        <div className="rp-sum-card">
          <div className="rp-sum-val">{stats.length}</div>
          <div className="rp-sum-label">Police Zones</div>
        </div>
        <div className="rp-sum-card">
          <div className="rp-sum-val">{fmt(totals.locations)}</div>
          <div className="rp-sum-label">Unique Locations</div>
        </div>
        <div className="rp-sum-card">
          <div className="rp-sum-val">{totals.violations ? fmtPct((totals.night / totals.violations) * 100) : '—'}</div>
          <div className="rp-sum-label">Night-time Share</div>
        </div>
      </div>

      {/* Chart */}
      <div className="rp-chart-card">
        <div className="rp-chart-header">
          <span className="rp-chart-title">Violations by Station</span>
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
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11 }}
              angle={-30}
              textAnchor="end"
              interval={0}
            />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={v => [fmt(v), CHART_OPTS.find(o => o.key === chartKey)?.label]} />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {chartData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Table */}
      <div className="rp-table-card">
        <table className="rp-table">
          <thead>
            <tr>
              <th className="rp-th">#</th>
              <Th k="police_station"    label="Station" />
              <Th k="total_violations"  label="Total Violations" />
              <Th k="unique_locations"  label="Unique Locations" />
              <Th k="night_violations"  label="Night Violations" />
              <th className="rp-th">Night Share</th>
              <th className="rp-th">Peak Hour</th>
              <th className="rp-th">Top Junction</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s, i) => {
              const nightShare = s.total_violations
                ? (s.night_violations / s.total_violations) * 100
                : 0;
              return (
                <tr key={s.police_station} className="rp-row">
                  <td className="rp-td rp-rank">
                    <span className="rp-rank-badge" style={{ background: COLORS[i % COLORS.length] }}>
                      {i + 1}
                    </span>
                  </td>
                  <td className="rp-td rp-station-name">{s.police_station || '—'}</td>
                  <td className="rp-td rp-num">{fmt(s.total_violations)}</td>
                  <td className="rp-td rp-num">{fmt(s.unique_locations)}</td>
                  <td className="rp-td rp-num">{fmt(s.night_violations)}</td>
                  <td className="rp-td rp-num">
                    <span className={`rp-pct-badge ${nightShare > 70 ? 'high' : nightShare > 50 ? 'mid' : 'low'}`}>
                      {fmtPct(nightShare)}
                    </span>
                  </td>
                  <td className="rp-td rp-num">{s.peak_hour != null ? `${s.peak_hour}:00` : '—'}</td>
                  <td className="rp-td rp-top-loc">{s.top_location || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
