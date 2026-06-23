# Complete Website Build Instructions
# Sugama Sanchara — AI Parking Enforcement Intelligence

This document covers everything needed to build the complete website — not just the
operational dashboard. There are two new pages (Home landing page + Reports page),
seven complete file rewrites, two backend fixes, and a cleanup of dead elements.

---

## OVERVIEW OF WHAT'S BEING BUILT

**Current state:** Single-page app with 3 tabs, several truncated files, dead buttons, no entry point.

**After these instructions:**
- `/` → Home page: hero, real stats, capability cards, CTA to dashboard
- Count Heatmap, Severity Heatmap, Impact Scores → fully working (truncated files completed)
- Reports → new page: station-level analytics, bar chart, CSV export
- All dead buttons removed (Bell, Settings, MoreVertical, Filter, Eye, user-avatar)
- ForecastPanel and AlertStrip wired into both heatmap pages
- PIS backend fixed: grid_ keys filtered, lat/lon in schema, Monitor tier works

**Nav order:** Home | Count Heatmap | Severity Heatmap | Impact Scores | Reports | API Docs ↗

---

## SECTION 1 — DELETE THESE FILES

These files exist but are imported nowhere. Delete them:

```
frontend-react/src/components/Dashboard.jsx
frontend-react/src/components/Dashboard.css
frontend-react/src/components/MapContainer.jsx
frontend-react/src/components/MapContainer.css
frontend-react/src/components/SidePanel.jsx
frontend-react/src/components/SidePanel.css
```

---

## SECTION 2 — BACKEND FIXES

### Fix A: `prediction_api/app/services/analytics_pipeline.py`

In `build_pis_and_profiles()`, find the line that reads the CSV and the bad-row filter.
Add a grid_ filter IMMEDIATELY after the bad-row drop so PIS tiers are computed on
named junctions only (~132 rows), not all 6333 location_keys.

Find this block (approximately lines 15–25):
```python
raw = pd.read_csv(csv_path)
# drop rows missing lat/lon
raw = raw.dropna(subset=["latitude", "longitude"]).copy()
```

Add after the dropna line:
```python
# Keep only named junctions — grid_X.XXX_Y.YYY cells are unnamed and pollute PIS tiers
raw = raw[~raw["location_key"].astype(str).str.startswith("grid_")].copy()
```

Then in the same function, find where the `rows` list is built (the `rows.append({...})` call).
Add `latitude` and `longitude` to that dict:

```python
rows.append({
    # ... existing keys ...
    "latitude":  float(grp["latitude"].iloc[0])  if "latitude"  in grp.columns else None,
    "longitude": float(grp["longitude"].iloc[0]) if "longitude" in grp.columns else None,
})
```

### Fix B: `prediction_api/app/schemas.py`

Find the `PISRecord` Pydantic model. Add two optional fields:

```python
class PISRecord(BaseModel):
    rank: int
    location_key: str
    area: Optional[str]
    police_station: Optional[str]
    pis_score: float
    vehicle_hours_lost_per_day: float
    loss_inr_per_day: float
    enforcement_failure_rate: float
    mean_blockage_severity: float
    betweenness: float
    action_type: str
    latitude: Optional[float] = None   # ADD THIS
    longitude: Optional[float] = None  # ADD THIS
```

After these fixes, restart the FastAPI server. The JunctionDrawer map will render,
and the Monitor filter in Impact Scores will return results.

---

## SECTION 3 — NEW PAGE: Home (`frontend-react/src/pages/HomePage.jsx`)

Create this file. It is the landing page — the first thing judges and officers see.
Uses real dataset stats (298,450 violations, 132 named junctions, 6 police zones, 6 months).

```jsx
import React from 'react';
import './HomePage.css';

const STATS = [
  { value: '2,98,450', label: 'Violations Analyzed', sub: 'Nov 2023 – Apr 2024' },
  { value: '132',      label: 'Named Junctions',     sub: 'Bengaluru city limits' },
  { value: '66.4%',   label: 'Night-time Violations', sub: '10 PM – 6 AM window' },
  { value: '6',       label: 'Police Zones',          sub: 'Station-level coverage' },
];

const CAPABILITIES = [
  {
    icon: '🗺️',
    title: 'Live Violation Heatmap',
    desc: 'LightGBM model predicts violation counts for every named junction at any target hour. Hotspots pulse on the map so patrol officers see priorities at a glance.',
    tag: 'Count Heatmap',
  },
  {
    icon: '⚠️',
    title: 'Severity Scoring',
    desc: 'A Tweedie regression model weighs vehicle class (PCU), lane blockage, and time-of-day to compute a severity score — not just how many violations, but how bad they are.',
    tag: 'Severity Heatmap',
  },
  {
    icon: '📊',
    title: 'Parking Impact Score',
    desc: 'Each junction gets a PIS: vehicle-hours lost per day, economic loss in ₹, enforcement failure rate, and network betweenness centrality. Ranks the 132 junctions by real-world impact.',
    tag: 'Impact Scores',
  },
  {
    icon: '🚗',
    title: 'Dark Fleet Detection',
    desc: 'Repeat offenders are clustered by recurrence pattern across junctions. Fleet leaders — vehicles appearing at multiple sites — are surfaced for targeted action.',
    tag: 'Enforcement Panel',
  },
  {
    icon: '📈',
    title: '24-Hour Forecast',
    desc: 'Parallel multi-horizon predictions for T+1h, T+2h, T+4h, T+8h, and T+24h across the top 5 hotspots. Rising/Easing/Stable badges tell officers what's coming.',
    tag: 'Forecast Panel',
  },
  {
    icon: '💬',
    title: 'AI Enforcement Assistant',
    desc: 'A Groq/Llama 3.3 70B chatbot with live prediction context injected. Ask "which junction needs a unit at 3am?" and get a grounded, data-backed answer.',
    tag: 'AI Chatbot',
  },
];

const HOW_IT_WORKS = [
  {
    step: '01',
    title: 'Ingest & Engineer',
    desc: '298,450 raw violation records cleaned, geocoded, and transformed into an 11-feature hourly panel: lag counts, rolling means, time cyclical encodings, and PCU-weighted severity.',
  },
  {
    step: '02',
    title: 'Predict',
    desc: 'LightGBM Poisson (count) and Tweedie (severity) models generate scores per junction per hour. Cold-start handled by baseline and naive fallbacks.',
  },
  {
    step: '03',
    title: 'Rank & Dispatch',
    desc: 'PIS ranking combines economic loss, vehicle hours wasted, enforcement gap, and road network centrality to give a single prioritized enforcement list per station.',
  },
];

export default function HomePage({ onNavigate }) {
  return (
    <div className="home-page">
      {/* Hero */}
      <section className="home-hero">
        <div className="home-hero-content">
          <div className="home-hero-badge">AI-Powered · Real Data · Bengaluru</div>
          <h1 className="home-hero-title">
            Parking Enforcement<br />
            <span className="home-hero-accent">Intelligence</span> for Traffic Police
          </h1>
          <p className="home-hero-desc">
            Detect illegal parking hotspots. Quantify their impact on traffic flow.
            Enable targeted, data-driven enforcement — not patrol-based guesswork.
          </p>
          <div className="home-hero-actions">
            <button className="home-cta-primary" onClick={() => onNavigate('prediction')}>
              Open Operations Center →
            </button>
            <button className="home-cta-secondary" onClick={() => onNavigate('reports')}>
              View Station Reports
            </button>
          </div>
        </div>
        <div className="home-hero-visual">
          <div className="home-hero-map-preview">
            <div className="hmp-dot hmp-dot-1" />
            <div className="hmp-dot hmp-dot-2" />
            <div className="hmp-dot hmp-dot-3" />
            <div className="hmp-dot hmp-dot-4" />
            <div className="hmp-dot hmp-dot-5" />
            <div className="hmp-pulse hmp-pulse-1" />
            <div className="hmp-pulse hmp-pulse-2" />
            <div className="hmp-grid" />
            <div className="hmp-label">Bengaluru</div>
          </div>
        </div>
      </section>

      {/* Stats bar */}
      <section className="home-stats">
        {STATS.map(s => (
          <div key={s.label} className="home-stat-card">
            <div className="home-stat-value">{s.value}</div>
            <div className="home-stat-label">{s.label}</div>
            <div className="home-stat-sub">{s.sub}</div>
          </div>
        ))}
      </section>

      {/* Capabilities */}
      <section className="home-section">
        <div className="home-section-header">
          <h2>What This System Does</h2>
          <p>Six integrated modules, one unified enforcement intelligence platform.</p>
        </div>
        <div className="home-caps-grid">
          {CAPABILITIES.map(c => (
            <div key={c.title} className="home-cap-card">
              <div className="home-cap-icon">{c.icon}</div>
              <div className="home-cap-tag">{c.tag}</div>
              <h3 className="home-cap-title">{c.title}</h3>
              <p className="home-cap-desc">{c.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="home-section home-hiw-section">
        <div className="home-section-header">
          <h2>How It Works</h2>
          <p>End-to-end pipeline from raw violation records to ranked enforcement dispatch.</p>
        </div>
        <div className="home-hiw-row">
          {HOW_IT_WORKS.map((h, i) => (
            <div key={h.step} className="home-hiw-card">
              <div className="home-hiw-step">{h.step}</div>
              <h3 className="home-hiw-title">{h.title}</h3>
              <p className="home-hiw-desc">{h.desc}</p>
              {i < HOW_IT_WORKS.length - 1 && <div className="home-hiw-arrow">→</div>}
            </div>
          ))}
        </div>
      </section>

      {/* CTA footer */}
      <section className="home-footer-cta">
        <h2>Ready to deploy?</h2>
        <p>The operations center is live. Data is loaded. Models are ready.</p>
        <button className="home-cta-primary large" onClick={() => onNavigate('prediction')}>
          Open Operations Center →
        </button>
      </section>
    </div>
  );
}
```

### Create `frontend-react/src/pages/HomePage.css`

```css
.home-page {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--bg-color);
}

/* Hero */
.home-hero {
  display: flex;
  align-items: center;
  gap: 60px;
  padding: 64px 80px;
  background: var(--panel-bg);
  border-bottom: 1px solid var(--border-color);
  min-height: 420px;
}

.home-hero-content { flex: 1; max-width: 560px; }

.home-hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #ede9fe;
  color: #6366f1;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  padding: 5px 12px;
  border-radius: 20px;
  margin-bottom: 20px;
}

.home-hero-title {
  font-size: 42px;
  font-weight: 800;
  color: var(--text-main);
  line-height: 1.15;
  margin-bottom: 18px;
}

.home-hero-accent { color: #6366f1; }

.home-hero-desc {
  font-size: 16px;
  color: var(--text-muted);
  line-height: 1.65;
  margin-bottom: 32px;
  max-width: 480px;
}

.home-hero-actions { display: flex; gap: 12px; flex-wrap: wrap; }

.home-cta-primary {
  background: #1f2937;
  color: #fff;
  border: none;
  border-radius: 10px;
  padding: 13px 28px;
  font-size: 14px;
  font-weight: 700;
  font-family: var(--font-family);
  cursor: pointer;
  transition: background 0.15s, transform 0.1s;
}
.home-cta-primary:hover { background: #111827; transform: translateY(-1px); }
.home-cta-primary.large { font-size: 16px; padding: 16px 36px; }

.home-cta-secondary {
  background: transparent;
  color: var(--text-main);
  border: 1.5px solid var(--border-color);
  border-radius: 10px;
  padding: 13px 28px;
  font-size: 14px;
  font-weight: 600;
  font-family: var(--font-family);
  cursor: pointer;
  transition: border-color 0.15s;
}
.home-cta-secondary:hover { border-color: #6366f1; color: #6366f1; }

/* Hero visual — abstract map dots */
.home-hero-visual { flex-shrink: 0; }

.home-hero-map-preview {
  width: 360px;
  height: 280px;
  background: #f8fafc;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  position: relative;
  overflow: hidden;
}

.hmp-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--border-color) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-color) 1px, transparent 1px);
  background-size: 36px 36px;
  opacity: 0.5;
}

.hmp-label {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--panel-bg);
  padding: 3px 10px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
}

.hmp-dot {
  position: absolute;
  border-radius: 50%;
  z-index: 2;
}
.hmp-dot-1 { width: 20px; height: 20px; background: #ef4444; top: 30%; left: 45%; box-shadow: 0 0 0 4px rgba(239,68,68,0.2); }
.hmp-dot-2 { width: 14px; height: 14px; background: #f59e0b; top: 50%; left: 60%; box-shadow: 0 0 0 3px rgba(245,158,11,0.2); }
.hmp-dot-3 { width: 14px; height: 14px; background: #f97316; top: 25%; left: 65%; box-shadow: 0 0 0 3px rgba(249,115,22,0.2); }
.hmp-dot-4 { width: 10px; height: 10px; background: #22c55e; top: 65%; left: 35%; }
.hmp-dot-5 { width: 10px; height: 10px; background: #22c55e; top: 40%; left: 28%; }

.hmp-pulse {
  position: absolute;
  border-radius: 50%;
  animation: hmppulse 2s ease-out infinite;
  z-index: 1;
}
.hmp-pulse-1 { width: 40px; height: 40px; border: 2px solid #ef4444; top: calc(30% - 10px); left: calc(45% - 10px); }
.hmp-pulse-2 { width: 28px; height: 28px; border: 2px solid #f59e0b; top: calc(50% - 7px); left: calc(60% - 7px); animation-delay: 0.8s; }

@keyframes hmppulse {
  0%   { transform: scale(1); opacity: 0.8; }
  100% { transform: scale(2.2); opacity: 0; }
}

/* Stats bar */
.home-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-bottom: 1px solid var(--border-color);
}

.home-stat-card {
  padding: 28px 32px;
  border-right: 1px solid var(--border-color);
  background: var(--panel-bg);
}
.home-stat-card:last-child { border-right: none; }

.home-stat-value {
  font-size: 32px;
  font-weight: 800;
  color: var(--text-main);
  line-height: 1;
  margin-bottom: 6px;
}

.home-stat-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 3px;
}

.home-stat-sub {
  font-size: 11px;
  color: var(--text-muted);
}

/* Sections */
.home-section { padding: 60px 80px; }

.home-hiw-section { background: var(--panel-bg); border-top: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); }

.home-section-header {
  margin-bottom: 36px;
}

.home-section-header h2 {
  font-size: 26px;
  font-weight: 800;
  color: var(--text-main);
  margin-bottom: 8px;
}

.home-section-header p {
  font-size: 14px;
  color: var(--text-muted);
}

/* Capabilities grid */
.home-caps-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.home-cap-card {
  background: var(--panel-bg);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 24px;
  transition: box-shadow 0.2s;
}
.home-cap-card:hover { box-shadow: 0 4px 20px rgba(0,0,0,0.08); }

.home-cap-icon { font-size: 28px; margin-bottom: 10px; }

.home-cap-tag {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: #6366f1;
  background: #ede9fe;
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  margin-bottom: 10px;
}

.home-cap-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-main);
  margin-bottom: 8px;
}

.home-cap-desc {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.6;
}

/* How it works */
.home-hiw-row {
  display: flex;
  gap: 0;
  align-items: flex-start;
  position: relative;
}

.home-hiw-card {
  flex: 1;
  position: relative;
  padding: 0 32px 0 0;
}

.home-hiw-step {
  font-size: 36px;
  font-weight: 900;
  color: #e5e7eb;
  line-height: 1;
  margin-bottom: 12px;
}

.home-hiw-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-main);
  margin-bottom: 10px;
}

.home-hiw-desc {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.65;
}

.home-hiw-arrow {
  position: absolute;
  right: 8px;
  top: 6px;
  font-size: 24px;
  color: #d1d5db;
}

/* Footer CTA */
.home-footer-cta {
  padding: 64px 80px;
  text-align: center;
  background: #1f2937;
}

.home-footer-cta h2 {
  font-size: 28px;
  font-weight: 800;
  color: #fff;
  margin-bottom: 10px;
}

.home-footer-cta p {
  font-size: 15px;
  color: #9ca3af;
  margin-bottom: 28px;
}
```

---

## SECTION 4 — NEW PAGE: Reports (`frontend-react/src/pages/ReportsPage.jsx`)

Pulls from the existing `/api/v1/station-stats` endpoint. Shows per-station violation
breakdown, a bar chart, and a CSV export button. No new backend work required.

```jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Loader2, Download } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid
} from 'recharts';
import './ReportsPage.css';

const fmt   = n => n == null ? '—' : Number(n).toLocaleString('en-IN');
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
```

### Create `frontend-react/src/pages/ReportsPage.css`

```css
.rp-page {
  height: 100%;
  overflow-y: auto;
  padding: 0 0 40px;
  background: var(--bg-color);
}

.rp-loading, .rp-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-muted);
  font-size: 14px;
}

.rp-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 32px 40px 24px;
  background: var(--panel-bg);
  border-bottom: 1px solid var(--border-color);
}

.rp-title {
  font-size: 22px;
  font-weight: 800;
  color: var(--text-main);
  margin-bottom: 6px;
}

.rp-sub {
  font-size: 13px;
  color: var(--text-muted);
}

.rp-export-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  background: #1f2937;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-family);
  cursor: pointer;
  flex-shrink: 0;
}
.rp-export-btn:hover { background: #111827; }

.rp-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-bottom: 1px solid var(--border-color);
}

.rp-sum-card {
  padding: 24px 32px;
  background: var(--panel-bg);
  border-right: 1px solid var(--border-color);
}
.rp-sum-card:last-child { border-right: none; }

.rp-sum-val {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-main);
  margin-bottom: 4px;
}

.rp-sum-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.rp-chart-card {
  margin: 24px 40px 0;
  background: var(--panel-bg);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 24px;
}

.rp-chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.rp-chart-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-main);
}

.rp-chart-toggles { display: flex; gap: 6px; }

.rp-chart-toggle {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-family);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}
.rp-chart-toggle:hover { color: #6366f1; border-color: #6366f1; }
.rp-chart-toggle.active { background: #ede9fe; color: #6366f1; border-color: #6366f1; }

.rp-table-card {
  margin: 16px 40px 0;
  background: var(--panel-bg);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  overflow: hidden;
}

.rp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.rp-th {
  padding: 12px 16px;
  text-align: left;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-muted);
  background: var(--bg-color);
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}
.rp-th:hover { color: var(--text-main); }
.rp-th-active { color: #6366f1 !important; }

.rp-row:hover { background: #f9fafb; }

.rp-td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  vertical-align: middle;
  color: var(--text-main);
}
.rp-row:last-child .rp-td { border-bottom: none; }

.rp-rank { width: 48px; }

.rp-rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.rp-station-name { font-weight: 600; }
.rp-num { text-align: right; font-variant-numeric: tabular-nums; }
.rp-top-loc { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-muted); font-size: 12px; }

.rp-pct-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
}
.rp-pct-badge.high { background: #fee2e2; color: #dc2626; }
.rp-pct-badge.mid  { background: #fef3c7; color: #d97706; }
.rp-pct-badge.low  { background: #dcfce7; color: #16a34a; }
```

---

## SECTION 5 — REWRITE: `frontend-react/src/App.jsx`

Completely replace the file. Adds Home and Reports pages, wires nav, keeps existing state.

```jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import TopNav from './components/TopNav';
import HomePage from './pages/HomePage';
import PredictionPage from './pages/PredictionPage';
import SeverityPage from './pages/SeverityPage';
import PISPage from './pages/PISPage';
import ReportsPage from './pages/ReportsPage';
import Chatbot from './components/Chatbot';
import './App.css';

export default function App() {
  const [activePage, setActivePage]           = useState('home');
  const [sharedPredictions, setSharedPredictions] = useState([]);
  const [searchQuery, setSearchQuery]         = useState('');
  const [selectedStation, setSelectedStation] = useState('');
  const [persistenceScores, setPersistenceScores] = useState({});

  useEffect(() => {
    axios.get('/api/v1/persistence', { timeout: 15000 })
      .then(r => setPersistenceScores(r.data || {}))
      .catch(() => {});
  }, []);

  const handlePageChange = page => {
    setActivePage(page);
    setSelectedStation('');
    setSearchQuery('');
  };

  const sharedProps = {
    onPredictionsLoaded: setSharedPredictions,
    searchQuery,
    selectedStation,
    onStationChange:     setSelectedStation,
    persistenceScores,
  };

  const showSearch = activePage === 'prediction' || activePage === 'severity';

  return (
    <div className="app-container">
      <TopNav
        activePage={activePage}
        setActivePage={handlePageChange}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        showSearch={showSearch}
      />
      <main className="main-content">
        {activePage === 'home'       && <HomePage       onNavigate={handlePageChange} />}
        {activePage === 'prediction' && <PredictionPage {...sharedProps} />}
        {activePage === 'severity'   && <SeverityPage   {...sharedProps} />}
        {activePage === 'pis'        && <PISPage />}
        {activePage === 'reports'    && <ReportsPage />}
      </main>
      {activePage !== 'home' && (
        <Chatbot predictions={sharedPredictions} activePage={activePage} />
      )}
    </div>
  );
}
```

---

## SECTION 6 — REWRITE: `frontend-react/src/components/TopNav.jsx`

Removes Bell, Settings, user-avatar. Adds Home and Reports nav links. Hides search bar on non-map pages.

```jsx
import React from 'react';
import { Search } from 'lucide-react';
import './TopNav.css';

export default function TopNav({ activePage, setActivePage, searchQuery, onSearchChange, showSearch }) {
  return (
    <header className="topnav">
      <div className="topnav-left">
        <div className="topnav-brand">
          <div className="brand-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-dept">Sugama Sanchara</span>
            <span className="brand-name">Bengaluru</span>
          </div>
        </div>

        <nav className="topnav-links">
          <button className={`nav-link ${activePage === 'home'       ? 'active' : ''}`} onClick={() => setActivePage('home')}>Home</button>
          <button className={`nav-link ${activePage === 'prediction' ? 'active' : ''}`} onClick={() => setActivePage('prediction')}>Count Heatmap</button>
          <button className={`nav-link ${activePage === 'severity'   ? 'active' : ''}`} onClick={() => setActivePage('severity')}>Severity Heatmap</button>
          <button className={`nav-link ${activePage === 'pis'        ? 'active' : ''}`} onClick={() => setActivePage('pis')}>Impact Scores</button>
          <button className={`nav-link ${activePage === 'reports'    ? 'active' : ''}`} onClick={() => setActivePage('reports')}>Reports</button>
          <span className="nav-divider">|</span>
          <a href="http://127.0.0.1:8001/docs" target="_blank" rel="noreferrer" className="nav-link">API Docs ↗</a>
        </nav>
      </div>

      {showSearch && (
        <div className="topnav-right">
          <div className="search-bar">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              placeholder="Search junctions / stations…"
              value={searchQuery}
              onChange={e => onSearchChange(e.target.value)}
            />
            {searchQuery && (
              <button className="search-clear" onClick={() => onSearchChange('')}>×</button>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
```

Also remove the `.user-avatar` CSS block from `TopNav.css` (it references the div we deleted).

---

## SECTION 7 — COMPLETE: `frontend-react/src/pages/PredictionPage.jsx`

The file truncates at `icon="pr`. APPEND the following starting from that exact point.
Replace the partial last line with this complete JSX return:

```jsx
  return (
    <div className="page-layout">
      <ControlsSidebar
        title="Count Heatmap"
        subtitle="Violation risk forecast"
        icon="prediction"
        statusColor={statusDot.color}
        statusLabel={statusDot.label}
        timestamp={timestamp}
        onTimestampChange={setTimestamp}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        onRun={handleRun}
        loading={loading}
        error={error}
        predictions={filteredPredictions}
        scoreColor="indigo"
        legend={{ lo: 'Low Risk', hi: 'High Risk', gradient: 'linear-gradient(to right, #22c55e, #f59e0b, #ef4444)' }}
        displayTopN={DISPLAY_TOP_N}
        stationOptions={stationOptions}
        selectedStation={selectedStation}
        onStationChange={onStationChange}
        showForecast={showForecast}
        onForecastToggle={() => setShowForecast(v => !v)}
      />

      <div className="map-section">
        {filteredPredictions.length > 0 && <AlertStrip forecastData={forecastData} />}
        <div className="map-inner">
          <HeatMap
            predictions={filteredPredictions}
            selectedModel={selectedModel}
            colorScheme="count"
            displayTopN={DISPLAY_TOP_N}
          />
          {loading && (
            <div className="map-loading-overlay">
              <Loader2 className="spin-icon" size={32} />
              <p>Fetching predictions…</p>
            </div>
          )}
        </div>
        {showForecast && filteredPredictions.length > 0 && (
          <div className="forecast-drawer">
            <ForecastPanel
              baseTimestamp={timestamp}
              apiBase={API_BASE}
              selectedModel={selectedModel}
              topLocations={top5}
              onForecastData={setForecastData}
            />
          </div>
        )}
      </div>

      <EnforcementSidebar
        predictions={filteredPredictions}
        selectedModel={selectedModel}
        colorScheme="count"
        showSeverityFields={false}
        persistenceScores={persistenceScores}
        selectedStation={selectedStation}
      />
    </div>
  );
};

export default PredictionPage;
```

---

## SECTION 8 — COMPLETE: `frontend-react/src/pages/SeverityPage.jsx`

The file truncates after the `timestamp={timestamp}` prop inside ControlsSidebar.
Replace everything from that point with:

```jsx
        onTimestampChange={setTimestamp}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        onRun={handleRun}
        loading={loading}
        error={error}
        predictions={filteredPredictions}
        scoreColor="amber"
        legend={{ lo: 'Low Severity', hi: 'High Severity', gradient: 'linear-gradient(to right, #10b981, #f59e0b, #ea580c, #dc2626)' }}
        displayTopN={DISPLAY_TOP_N}
        stationOptions={stationOptions}
        selectedStation={selectedStation}
        onStationChange={onStationChange}
        showForecast={showForecast}
        onForecastToggle={() => setShowForecast(v => !v)}
        extraContent={sevHealth && <ConfidenceBanner health={sevHealth} />}
      />

      <div className="map-section">
        {filteredPredictions.length > 0 && <AlertStrip forecastData={forecastData} />}
        <div className="map-inner">
          <HeatMap
            predictions={filteredPredictions}
            selectedModel={selectedModel}
            colorScheme="severity"
            displayTopN={DISPLAY_TOP_N}
          />
          {loading && (
            <div className="map-loading-overlay">
              <Loader2 className="spin-icon" size={32} />
              <p>Fetching severity predictions…</p>
            </div>
          )}
        </div>
        {showForecast && filteredPredictions.length > 0 && (
          <div className="forecast-drawer">
            <ForecastPanel
              baseTimestamp={timestamp}
              apiBase={SEV_API}
              selectedModel={selectedModel}
              topLocations={top5}
              onForecastData={setForecastData}
            />
          </div>
        )}
      </div>

      <EnforcementSidebar
        predictions={filteredPredictions}
        selectedModel={selectedModel}
        colorScheme="severity"
        showSeverityFields={true}
        persistenceScores={persistenceScores}
        selectedStation={selectedStation}
      />
    </div>
  );
};

export default SeverityPage;
```

---

## SECTION 9 — COMPLETE: `frontend-react/src/components/ControlsSidebar.jsx`

The file cuts off at the `{/* N` comment near the bottom of the Night Mode section.
Replace everything from that comment onward with:

```jsx
        {/* Night Mode Chart */}
        {nightMode && (
          <section className="cs-section cs-night-chart-section">
            {hourlyLoading ? (
              <div className="cs-chart-loading">
                <Loader2 size={12} className="spin-icon" /> Loading hourly profile…
              </div>
            ) : hourlyData.length > 0 ? (
              <>
                <p className="cs-chart-loc">
                  {topLocationKey?.replace(/^[A-Z0-9]+ - /, '') || '—'}
                </p>
                <ResponsiveContainer width="100%" height={90}>
                  <BarChart data={hourlyData} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
                    <XAxis dataKey="hour" tick={{ fontSize: 9 }} interval={3} />
                    <YAxis tick={{ fontSize: 9 }} />
                    <Tooltip
                      formatter={v => [v.toFixed(1), 'Avg violations']}
                      labelFormatter={h => `Hour ${h}:00`}
                    />
                    <Bar dataKey="mean_violations" radius={[2, 2, 0, 0]}>
                      {hourlyData.map((entry, i) => (
                        <Cell key={i} fill={NIGHT_HOURS.has(entry.hour) ? '#6366f1' : '#d1d5db'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p className="cs-night-note">Purple = night hours (10 PM–6 AM)</p>
              </>
            ) : null}
          </section>
        )}

      </div>{/* end cs-scroll-body */}

      {/* Run + Forecast — fixed at bottom outside scroll */}
      <div className="cs-actions-fixed">
        <button className="cs-run-btn" onClick={onRun} disabled={loading}>
          {loading ? <Loader2 size={16} className="spin-icon" /> : <Play size={16} />}
          {loading ? 'Running…' : 'Run Prediction'}
        </button>

        {predictions.length > 0 && (
          <button
            className={`cs-forecast-btn ${showForecast ? 'active' : ''}`}
            onClick={onForecastToggle}
          >
            <TrendingUp size={14} />
            {showForecast ? 'Hide Forecast' : '24h Forecast'}
          </button>
        )}

        {error && <div className="cs-error">⚠ {error}</div>}
      </div>

      {/* Top 20 locations */}
      {top20.length > 0 && (
        <div className="cs-top-section">
          <div className="cs-section-header" style={{ padding: '10px 20px 6px' }}>
            <span className="cs-section-icon">📍</span>
            <h3>Top Locations</h3>
          </div>
          <ul className="cs-top-list">
            {top20.map((p, i) => {
              const score = p[key] || 0;
              const ratio = effectiveMax > 0 ? score / effectiveMax : 0;
              const color = colorFn(ratio);
              return (
                <li key={p.location_key} className="cs-top-item">
                  <span className="cs-top-rank" style={{ background: color }}>{i + 1}</span>
                  <div className="cs-top-info">
                    <div className="cs-top-name">{p.location_key.replace(/^[A-Z0-9]+ - /, '')}</div>
                    <div className="cs-top-meta">{p.police_station || p.area || '—'}</div>
                  </div>
                  <div className="cs-top-score-wrap">
                    <div className="cs-top-score">{score.toFixed(1)}</div>
                    <div className="cs-top-bar-track">
                      <div className="cs-top-bar-fill" style={{ width: `${Math.round(ratio * 100)}%`, background: color }} />
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Footer stats */}
      <div className="cs-stats">
        <div className="cs-stat-item">
          <span>Locations</span>
          <strong>{predictions.length.toLocaleString()}</strong>
        </div>
        <div className="cs-stat-item">
          <span>Peak Score</span>
          <strong>{maxScore.toFixed(1)}</strong>
        </div>
      </div>
    </aside>
  );
};

export default ControlsSidebar;
```

Also add these rules to `ControlsSidebar.css`:

```css
.cs-actions-fixed {
  padding: 12px 20px;
  border-top: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.cs-forecast-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-family);
  cursor: pointer;
  transition: all 0.15s;
}
.cs-forecast-btn:hover { border-color: #6366f1; color: #6366f1; }
.cs-forecast-btn.active { background: #ede9fe; color: #6366f1; border-color: #6366f1; }

.cs-night-chart-section { padding-top: 12px; }

.cs-chart-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
  padding: 8px 0;
}

.cs-chart-loc {
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cs-night-note {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 4px;
}
```

---

## SECTION 10 — REWRITE: `frontend-react/src/components/EnforcementSidebar.jsx`

Complete rewrite. Removes: `Filter` header button, `MoreVertical` card button.
Keeps: dispatch → Google Maps, persistence badges, compact list (ranks 4–10),
dark fleet section, footer with last-fetch timestamp.

```jsx
import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { scoreKey, riskColor, sevRiskColor, VEH_SHORT } from '../utils/colorUtils';
import './EnforcementSidebar.css';

const SEVERITY_TAGS = ['CRITICAL', 'ELEVATED', 'MONITORING'];

export default function EnforcementSidebar({
  predictions, selectedModel, colorScheme, showSeverityFields,
  persistenceScores = {}, selectedStation = '',
}) {
  const key       = scoreKey(selectedModel);
  const colorFn   = colorScheme === 'severity' ? sevRiskColor : riskColor;
  const primary   = colorScheme === 'severity' ? '#f59e0b' : '#6366f1';

  const [darkFleet,      setDarkFleet]      = useState([]);
  const [fleetOpen,      setFleetOpen]      = useState(false);
  const [fleetLoading,   setFleetLoading]   = useState(false);
  const [lastFetchTime,  setLastFetchTime]  = useState(null);

  const sorted    = [...predictions].sort((a, b) => (b[key] || 0) - (a[key] || 0));
  const top10     = sorted.slice(0, 10);
  const globalMax = Math.max(...predictions.map(p => p[key] || 0), 1e-6);

  const getTags = idx => ({
    label: SEVERITY_TAGS[idx] || 'MONITORING',
    cls:  ['tag-critical', 'tag-elevated', 'tag-monitoring'][idx] || 'tag-monitoring',
  });

  const getBadge = loc => {
    const score = persistenceScores[loc.location_key];
    if (score === undefined) return null;
    if (score >= 0.9) return { label: 'Chronic', cls: 'badge-chronic' };
    if (score < 0.6)  return { label: 'Periodic', cls: 'badge-periodic' };
    return null;
  };

  useEffect(() => {
    if (predictions.length === 0) return;
    const url = selectedStation
      ? `/api/v1/dark-fleet?police_station=${encodeURIComponent(selectedStation)}&top_n=10`
      : '/api/v1/dark-fleet?top_n=10';
    setFleetLoading(true);
    axios.get(url, { timeout: 10000 })
      .then(r => { setDarkFleet(r.data || []); setLastFetchTime(Date.now()); })
      .catch(() => setDarkFleet([]))
      .finally(() => setFleetLoading(false));
  }, [selectedStation, predictions.length]);

  return (
    <aside className="enforcement-sidebar">
      <div className="es-header">
        <h2>Enforcement</h2>
      </div>

      <div className="es-body">
        {top10.length === 0 ? (
          <div className="es-empty">
            <p>Run a prediction to see enforcement alerts</p>
          </div>
        ) : (
          <>
            {/* Top 3 full alert cards */}
            {top10.slice(0, 3).map((pred, idx) => {
              const { label: tagLabel, cls: tagCls } = getTags(idx);
              const score         = pred[key] || 0;
              const pct           = Math.min(99, Math.round((score / globalMax) * 100));
              const violations    = Math.max(1, Math.round(pred.naive_prediction || pred.baseline_prediction || 1));
              const color         = colorFn(score / globalMax);
              const badge         = getBadge(pred);
              const name          = pred.location_key.replace(/^[A-Z0-9]+ - /, '');
              const lat           = pred.latitude;
              const lon           = pred.longitude;

              return (
                <div key={pred.location_key} className="es-alert-card">
                  <div className="es-card-header">
                    <span className={`es-tag ${tagCls}`}>{tagLabel}</span>
                    {badge && <span className={`es-persist-badge ${badge.cls}`}>{badge.label}</span>}
                  </div>

                  <h3 className="es-district">{name}</h3>
                  <div className="es-location-key">{pred.police_station || pred.area || ''}</div>

                  <div className="es-stats-row">
                    <div className="es-stat">
                      <span className="es-stat-label">Blockage Severity</span>
                      <div className="es-stat-val">
                        <span className="es-icon-bars" style={{ color }}>▐▌▐</span>
                        {pct}%
                      </div>
                    </div>
                    <div className="es-stat">
                      <span className="es-stat-label">Predicted Violations</span>
                      <div className="es-stat-val">
                        <span className="es-icon-p" style={{ background: color }}>P</span>
                        {violations}
                      </div>
                    </div>
                  </div>

                  {showSeverityFields && (
                    <div className="es-sev-row">
                      {pred.dominant_vehicle_cat && (
                        <div className="es-sev-item">
                          <span className="es-sev-label">Vehicle</span>
                          <span className="es-sev-val">{VEH_SHORT[pred.dominant_vehicle_cat] || pred.dominant_vehicle_cat}</span>
                        </div>
                      )}
                      {pred.lane_count != null && (
                        <div className="es-sev-item">
                          <span className="es-sev-label">Lanes</span>
                          <span className="es-sev-val">{pred.lane_count.toFixed(1)}</span>
                        </div>
                      )}
                      {pred.dominant_violation && (
                        <div className="es-sev-item es-sev-wide">
                          <span className="es-sev-label">Common Violation</span>
                          <span className="es-sev-val es-sev-trunc">{pred.dominant_violation}</span>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="es-risk-bar">
                    <div className="es-risk-fill" style={{ width: `${pct}%`, background: color }} />
                  </div>

                  {lat && lon && (
                    <button
                      className="es-dispatch-btn"
                      style={{ background: primary }}
                      onClick={() => window.open(`https://maps.google.com/?q=${lat},${lon}`, '_blank')}
                    >
                      Open in Maps
                    </button>
                  )}
                </div>
              );
            })}

            {/* Ranks 4–10 compact list */}
            {top10.length > 3 && (
              <div className="es-compact-section">
                <div className="es-compact-header">Next Locations</div>
                <ul className="es-compact-list">
                  {top10.slice(3).map((pred, i) => {
                    const score = pred[key] || 0;
                    const color = colorFn(score / globalMax);
                    const pct   = Math.round((score / globalMax) * 100);
                    return (
                      <li key={pred.location_key} className="es-compact-item">
                        <span className="es-compact-rank" style={{ background: color }}>{i + 4}</span>
                        <div className="es-compact-info">
                          <span className="es-compact-name">
                            {pred.location_key.replace(/^[A-Z0-9]+ - /, '')}
                          </span>
                          <div className="es-compact-bar-track">
                            <div className="es-compact-bar-fill" style={{ width: `${pct}%`, background: color }} />
                          </div>
                        </div>
                        <span className="es-compact-score">{score.toFixed(1)}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Dark Fleet */}
            <div className="es-fleet-section">
              <button className="es-fleet-toggle" onClick={() => setFleetOpen(o => !o)}>
                <AlertTriangle size={14} />
                Repeat Offenders
                {darkFleet.length > 0 && (
                  <span className="es-fleet-count">{darkFleet.length}</span>
                )}
                {fleetOpen
                  ? <ChevronDown size={14} style={{ marginLeft: 'auto' }} />
                  : <ChevronRight size={14} style={{ marginLeft: 'auto' }} />}
              </button>

              {fleetOpen && (
                <div className="es-fleet-body">
                  {fleetLoading ? (
                    <p className="es-fleet-empty">Loading…</p>
                  ) : darkFleet.length === 0 ? (
                    <p className="es-fleet-empty">
                      No repeat offenders{selectedStation ? ` in ${selectedStation}` : ''}.
                    </p>
                  ) : (
                    <ul className="es-fleet-list">
                      {darkFleet.map(v => (
                        <li key={v.vehicle_number} className="es-fleet-item">
                          <div className="es-fleet-vehicle">
                            {v.vehicle_number.slice(-8)}
                            {v.is_fleet_leader && (
                              <span className="es-fleet-leader">Fleet Lead</span>
                            )}
                          </div>
                          <div className="es-fleet-meta">
                            <span>{v.total_hits} hits</span>
                            <span>{v.distinct_junctions} junctions</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <div className="es-footer">
        <span>{predictions.length.toLocaleString()} locations scored</span>
        {lastFetchTime && (
          <span className="es-last-updated">
            Updated {new Date(lastFetchTime).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>
    </aside>
  );
}
```

Add/update in `EnforcementSidebar.css` — replace the `.es-footer` block with:

```css
.es-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--panel-bg);
  flex-shrink: 0;
}

.es-last-updated { color: var(--text-muted); }

.es-compact-section {
  background: var(--panel-bg);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
}

.es-compact-header {
  padding: 8px 14px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  background: var(--bg-color);
  border-bottom: 1px solid var(--border-color);
}

.es-compact-list { list-style: none; }

.es-compact-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border-color);
}
.es-compact-item:last-child { border-bottom: none; }

.es-compact-rank {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.es-compact-info { flex: 1; min-width: 0; }

.es-compact-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
  margin-bottom: 3px;
}

.es-compact-bar-track {
  height: 3px;
  background: var(--border-color);
  border-radius: 2px;
  overflow: hidden;
}

.es-compact-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

.es-compact-score {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  flex-shrink: 0;
}
```

---

## SECTION 11 — SUMMARY: What Changed and What Was Removed

**New files created:**
- `src/pages/HomePage.jsx` + `HomePage.css`
- `src/pages/ReportsPage.jsx` + `ReportsPage.css`

**Files completely rewritten:**
- `src/App.jsx` — adds Home + Reports routing, fixes truncation
- `src/components/TopNav.jsx` — removes Bell/Settings/user-avatar, adds Home+Reports nav links
- `src/components/EnforcementSidebar.jsx` — removes Filter/MoreVertical buttons, completes truncated render

**Files appended to (completions):**
- `src/pages/PredictionPage.jsx` — JSX return added (was cut off at `icon="pr`)
- `src/pages/SeverityPage.jsx` — JSX return completed
- `src/components/ControlsSidebar.jsx` — night chart, Run button, Forecast toggle, top list, footer added

**Backend fixes:**
- `analytics_pipeline.py` — grid_ filter added, lat/lon added to row dict
- `schemas.py` — latitude/longitude added to PISRecord

**Buttons removed (dead elements):**
- `<Bell />` icon button (TopNav)
- `<Settings />` icon button (TopNav)
- `user-avatar` div (TopNav)
- `<Filter />` header button (EnforcementSidebar)
- `<MoreVertical />` card menu button (EnforcementSidebar)

**Files deleted:**
- `Dashboard.jsx`, `Dashboard.css`, `MapContainer.jsx`, `MapContainer.css`, `SidePanel.jsx`, `SidePanel.css`

---

## QUICK VERIFICATION CHECKLIST

After implementing, confirm:
1. `npm run dev` starts without errors
2. Home page loads at `/` with stats and two CTA buttons that navigate correctly
3. Count Heatmap: Run Prediction → map fills → top 10 in enforcement sidebar → "Open in Maps" works
4. "24h Forecast" button appears after predictions load → panel slides in with line chart
5. Severity Heatmap: same as above but amber color scheme
6. Impact Scores → Monitor filter returns results (backend restart required after Python fix)
7. Reports → bar chart renders, CSV export downloads a file
8. No dead buttons visible anywhere in the UI
