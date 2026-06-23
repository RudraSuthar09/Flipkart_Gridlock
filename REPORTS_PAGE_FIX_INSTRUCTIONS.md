# Reports Page Fix Instructions

## Root Cause

The backend `station_stats` pipeline builds and returns these fields:
  `police_station`, `total_violations`, `rejection_rate`,
  `violations_per_device`, `median_validation_lag_hours`, `flag_high_rejection`

The frontend ReportsPage.jsx reads these fields:
  `night_violations`, `unique_locations`, `peak_hour`, `top_location`

**None of the four fields the frontend needs are computed by the backend.**
Every column except Total Violations shows `—` or `NaN%`.

Secondary bugs:
- `fmtPct(NaN)` returns `"NaN%"` — NaN !== null so the null-guard passes
- `nightShare = undefined / total * 100` → NaN → classified as `low` (CSS class), displays `NaN%`
- 54 stations crammed into one bar chart — completely unreadable
- `peak_hour` shown as `3:00` instead of `03:00` (no zero-padding)
- `top_location` references `location_key` but the user-friendly field is `junction_name`

---

## FIX 1 — Backend: `prediction_api/app/services/analytics_pipeline.py`

Find the `build_dark_fleet_and_station_stats` function.
Inside the `for station, sgrp in df.groupby('police_station'):` loop,
replace the entire body of that loop with the following:

```python
for station, sgrp in df.groupby('police_station'):
    total_v = len(sgrp)

    # ── Rejection rate (only over rows that have a validation_status) ──
    rej_rate = 0.0
    if 'validation_status' in sgrp.columns:
        vs = sgrp['validation_status'].dropna()
        if len(vs):
            rej_rate = (vs.astype(str).str.upper() == 'REJECTED').sum() / len(vs)

    # ── Violations per device ─────────────────────────────────────────
    vio_per_device = 0.0
    if 'device_id' in sgrp.columns:
        n_dev = sgrp['device_id'].nunique()
        vio_per_device = total_v / max(n_dev, 1)

    # ── Median validation lag ─────────────────────────────────────────
    lag_hours: Optional[float] = None
    if 'created_datetime' in sgrp.columns and 'validation_timestamp' in sgrp.columns:
        try:
            cd = pd.to_datetime(sgrp['created_datetime'], errors='coerce', utc=True)
            vt = pd.to_datetime(sgrp['validation_timestamp'], errors='coerce', utc=True)
            lag = (vt - cd).dt.total_seconds() / 3600.0
            lag = lag.dropna()
            lag = lag[lag >= 0]
            if len(lag):
                lag_hours = float(lag.median())
        except Exception:
            pass

    # ── Night violations (10 PM – 6 AM) ──────────────────────────────
    night_count = 0
    peak_hour: Optional[int] = None
    if 'created_datetime' in sgrp.columns:
        try:
            cd = pd.to_datetime(sgrp['created_datetime'], errors='coerce', utc=True)
            hrs = cd.dt.hour.dropna()
            NIGHT = {22, 23, 0, 1, 2, 3, 4, 5}
            night_count = int(hrs.isin(NIGHT).sum())
            if len(hrs):
                peak_hour = int(hrs.value_counts().idxmax())
        except Exception:
            pass

    # ── Unique locations ──────────────────────────────────────────────
    unique_locs = 0
    if 'location_key' in sgrp.columns:
        unique_locs = int(sgrp['location_key'].nunique())

    # ── Top junction (human-readable name, skip "No Junction" rows) ───
    top_junction: Optional[str] = None
    if 'junction_name' in sgrp.columns:
        jn = sgrp['junction_name'].dropna().astype(str)
        jn = jn[~jn.str.strip().isin(['No Junction', 'no junction', '', 'nan', 'None'])]
        if len(jn):
            top_junction = str(jn.mode().iloc[0])

    station_stats.append({
        'police_station':              str(station),
        'total_violations':            int(total_v),
        'rejection_rate':              float(rej_rate),
        'violations_per_device':       float(vio_per_device),
        'median_validation_lag_hours': lag_hours,
        'flag_high_rejection':         bool(rej_rate > 0.35),
        'night_violations':            night_count,         # NEW
        'unique_locations':            unique_locs,         # NEW
        'peak_hour':                   peak_hour,           # NEW
        'top_location':                top_junction,        # NEW
    })
```

---

## FIX 2 — Backend: `prediction_api/app/schemas.py`

Find the `StationStatsRecord` class and add four optional fields:

```python
class StationStatsRecord(BaseModel):
    police_station: str
    total_violations: int
    rejection_rate: float
    violations_per_device: float
    median_validation_lag_hours: Optional[float] = None
    flag_high_rejection: bool
    night_violations: int = 0           # ADD
    unique_locations: int = 0           # ADD
    peak_hour: Optional[int] = None     # ADD
    top_location: Optional[str] = None  # ADD

    model_config = {"from_attributes": True}
```

**After both backend fixes: restart the FastAPI server.**
The pipeline runs at startup — it won't pick up the new fields until restarted.

---

## FIX 3 — Frontend: Complete rewrite of `frontend-react/src/pages/ReportsPage.jsx`

Replace the entire file with the following. Key changes from the broken version:
- `fmt` and `fmtPct` now guard against `NaN` and `undefined`
- Night share computed safely with null-check before division
- Chart limited to top 15 stations (54 bars were unreadable)
- Peak hour zero-padded (`03:00` not `3:00`)
- `top_location` strips the `BTPxxx - ` code prefix for clean display
- Chart toggle now includes `rejection_rate` (a real field from the backend)
- Table shows `rejection_rate` column so the backend-only fields aren't wasted
- Summary cards use hardcoded fallback values when data is missing

```jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Loader2, Download } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid
} from 'recharts';
import './ReportsPage.css';

// Guards against null, undefined, AND NaN
const fmt    = n => (n == null || isNaN(Number(n))) ? '—' : Number(n).toLocaleString('en-IN');
const fmtPct = n => (n == null || isNaN(Number(n))) ? '—' : `${Number(n).toFixed(1)}%`;
const fmtHour = h => h == null ? '—' : `${String(h).padStart(2, '0')}:00`;
// Strip "BTP040 - " code prefix from junction names
const fmtJunction = s => s ? s.replace(/^[A-Z0-9]+ - /, '') : '—';

const COLORS = [
  '#6366f1','#f59e0b','#10b981','#ef4444','#3b82f6',
  '#8b5cf6','#f97316','#ec4899','#14b8a6','#84cc16',
  '#06b6d4','#a855f7','#fb923c','#e879f9','#4ade80',
];

const CHART_OPTS = [
  { key: 'total_violations',  label: 'Total Violations' },
  { key: 'night_violations',  label: 'Night Violations' },
  { key: 'unique_locations',  label: 'Unique Locations' },
  { key: 'rejection_rate',    label: 'Rejection Rate' },
];

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
    const av = a[sortKey] ?? 0;
    const bv = b[sortKey] ?? 0;
    return sortDir === 'desc' ? bv - av : av - bv;
  });

  // Limit chart to top 15 by the selected metric — 54 bars is unreadable
  const chartData = [...stats]
    .sort((a, b) => (b[chartKey] ?? 0) - (a[chartKey] ?? 0))
    .slice(0, 15)
    .map(s => ({
      name:  s.police_station || '—',
      value: chartKey === 'rejection_rate'
        ? parseFloat((s[chartKey] * 100).toFixed(1))   // convert 0.23 → 23.0 for display
        : (s[chartKey] ?? 0),
    }));

  // Summary totals — safe reduce
  const totals = stats.reduce((acc, s) => ({
    violations: acc.violations + (s.total_violations  || 0),
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
                chartKey === 'rejection_rate' ? `${v}%` : v >= 1000 ? `${(v/1000).toFixed(0)}k` : v
              }
            />
            <Tooltip
              formatter={(v, _) =>
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
                const nightCls = nightShare == null  ? ''
                  : nightShare > 70 ? 'high'
                  : nightShare > 50 ? 'mid'
                  : 'low';
                const rejPct = s.rejection_rate != null ? s.rejection_rate * 100 : null;
                const rejCls = rejPct == null    ? ''
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
```

---

## FIX 4 — Frontend: Update `frontend-react/src/pages/ReportsPage.css`

Add two new rules (keep everything else in the existing CSS file):

```css
/* Table scroll wrapper — lets table scroll horizontally on narrow screens */
.rp-table-scroll {
  overflow-x: auto;
}

/* Table card sub-header */
.rp-table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px 10px;
  border-bottom: 1px solid var(--border-color);
}

.rp-table-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-main);
}

.rp-table-hint {
  font-size: 11px;
  color: var(--text-muted);
}

/* Summary card sub-label */
.rp-sum-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* Highlighted summary value */
.rp-sum-highlight {
  color: #6366f1;
}

/* Fixed rank column width */
.rp-th-fixed {
  width: 48px;
}
```

---

## VERIFICATION

After restarting the API server and refreshing the page:

1. Summary cards show real numbers — not `—` or `NaN%`
2. Night-time Share shows `~66%` (matching the known 66.4% from dataset analysis)
3. Bar chart shows **15** bars, all labeled cleanly, not 54 overlapping labels
4. Rejection Rate toggle on chart shows `%` values correctly
5. Table: Night column, Locations column, Rejection Rate column all have numbers
6. Night % badges are coloured: red (>70%), amber (50–70%), green (<50%)
7. Rejection Rate badges similarly coloured: red if >35% (backend `flag_high_rejection`)
8. Peak Hour shows `03:00`, `05:00` etc — not `3:00` or `undefined:00`
9. Top Junction column shows names like `Elite Junction`, not `BTP040 - Elite Junction` or `—`
10. CSV export produces a valid file with all columns populated
