import React from 'react';
import './HomePage.css';

const STATS = [
  { value: '2,98,450', label: 'Violations Recorded',    sub: 'Nov 2023 – Apr 2024' },
  { value: '132',      label: 'Named Junctions',        sub: 'Across Bengaluru' },
  { value: '66.4%',   label: 'Night-time Share',        sub: '10 PM – 6 AM window' },
  { value: '6',       label: 'Police Zones',            sub: 'Full station coverage' },
];

const MODULES = [
  {
    num: '01',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="22" height="22">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
        <circle cx="12" cy="10" r="3"/>
      </svg>
    ),
    title: 'Count Heatmap',
    desc: 'LightGBM Poisson model scores every junction per hour. Officers see ranked hotspots at a glance before dispatch.',
    page: 'prediction',
  },
  {
    num: '02',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="22" height="22">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    ),
    title: 'Severity Heatmap',
    desc: 'Tweedie regression weighs vehicle class, lane blockage and time-of-day — measuring impact, not just count.',
    page: 'severity',
  },
  {
    num: '03',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="22" height="22">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>
        <line x1="6" y1="20" x2="6" y2="14"/>
      </svg>
    ),
    title: 'Impact Scores',
    desc: 'Parking Impact Score ranks junctions by vehicle-hours lost, economic loss in ₹, enforcement failure rate and road centrality.',
    page: 'pis',
  },
  {
    num: '04',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="22" height="22">
        <rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8l5 3-5 3V8z"/>
      </svg>
    ),
    title: 'Route Risk',
    desc: 'Score any origin-to-destination route by aggregating severity across all junctions the route passes through.',
    page: 'route',
  },
  {
    num: '05',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="22" height="22">
        <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>
      </svg>
    ),
    title: 'Officer Deployment',
    desc: 'Greedy maximum-coverage optimizer assigns available officers to hotspot clusters to maximise junction coverage.',
    page: 'deployment',
  },
  {
    num: '06',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="22" height="22">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
        <polyline points="10 9 9 9 8 9"/>
      </svg>
    ),
    title: 'Station Reports',
    desc: 'Per-station violation breakdown with bar charts, night-time share and CSV export for operational reporting.',
    page: 'reports',
  },
];

const PIPELINE = [
  {
    step: 'INGEST',
    title: 'Data Collection',
    body: '298,450 raw challan records, geocoded and timestamped, joined to road network and lane metadata.',
  },
  {
    step: 'ENGINEER',
    title: 'Feature Pipeline',
    body: '11 hourly features per junction: lag counts, rolling means, PCU-weighted severity, cyclical time encodings.',
  },
  {
    step: 'PREDICT',
    title: 'ML Inference',
    body: 'LightGBM Poisson (count) and Tweedie (severity) models. Baseline and naïve fallbacks for cold-start.',
  },
  {
    step: 'RANK',
    title: 'Enforcement Dispatch',
    body: 'PIS combines economic loss, vehicle hours wasted, enforcement gap and betweenness to produce a ranked list per station.',
  },
];

export default function HomePage({ onNavigate }) {
  return (
    <div className="hp-root">

      {/* ── Hero banner ─────────────────────────────── */}
      <section className="hp-hero">
        <div className="hp-hero-inner">
          <div className="hp-hero-left">
            <div className="hp-eyebrow">
              <span className="hp-eyebrow-line" />
              Bengaluru Traffic Police · Analytical Intelligence
            </div>
            <h1 className="hp-hero-h1">
              Sugama Sanchara<br />
              <span className="hp-hero-h1-accent">Enforcement Intelligence</span>
            </h1>
            <p className="hp-hero-p">
              Data-driven parking enforcement for 132 named junctions across
              Bengaluru. Predict violations, quantify impact, deploy officers
              where they matter most.
            </p>
            <div className="hp-hero-actions">
              <button className="hp-btn-primary" onClick={() => onNavigate('prediction')}>
                Open Operations Dashboard
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                  <path d="M3 8h10M9 4l4 4-4 4"/>
                </svg>
              </button>
              <button className="hp-btn-ghost" onClick={() => onNavigate('reports')}>
                Station Reports
              </button>
            </div>
          </div>

          <div className="hp-hero-right">
            <div className="hp-dashboard-preview">
              <div className="hdp-topbar">
                <div className="hdp-dot hdp-dot-r" /><div className="hdp-dot hdp-dot-y" /><div className="hdp-dot hdp-dot-g" />
                <span className="hdp-topbar-label">Live Operations · Bengaluru</span>
              </div>
              <div className="hdp-map-full">
                {/* Real map screenshot as background */}
                <img
                  src="/map-preview.png"
                  alt="Bengaluru heatmap"
                  className="hdp-map-img"
                />
                {/* Animated pulse dots overlay — mimicking real hotspot positions */}
                <div className="hdp-overlay-dot hdp-od-red"    style={{ top: '42%', left: '38%' }} />
                <div className="hdp-overlay-dot hdp-od-orange" style={{ top: '55%', left: '43%' }} />
                <div className="hdp-overlay-dot hdp-od-orange" style={{ top: '32%', left: '45%' }} />
                <div className="hdp-overlay-dot hdp-od-amber"  style={{ top: '36%', left: '58%' }} />
                <div className="hdp-overlay-dot hdp-od-amber"  style={{ top: '48%', left: '55%' }} />
                <div className="hdp-overlay-dot hdp-od-green"  style={{ top: '18%', left: '48%' }} />
                <div className="hdp-overlay-dot hdp-od-green"  style={{ top: '40%', left: '28%' }} />
                <div className="hdp-overlay-dot hdp-od-olive"  style={{ top: '64%', left: '40%' }} />
                <div className="hdp-overlay-dot hdp-od-olive"  style={{ top: '72%', left: '52%' }} />
                {/* Primary pulse ring on top hotspot */}
                <div className="hdp-overlay-pulse hdp-pulse-red"    style={{ top: 'calc(42% - 10px)', left: 'calc(38% - 10px)' }} />
                <div className="hdp-overlay-pulse hdp-pulse-orange"  style={{ top: 'calc(55% - 8px)',  left: 'calc(43% - 8px)',  animationDelay: '0.7s' }} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Key metrics strip ────────────────────────── */}
      <section className="hp-metrics">
        {STATS.map((s) => (
          <div key={s.label} className="hp-metric">
            <div className="hp-metric-val">{s.value}</div>
            <div className="hp-metric-label">{s.label}</div>
            <div className="hp-metric-sub">{s.sub}</div>
          </div>
        ))}
      </section>

      {/* ── Modules grid ─────────────────────────────── */}
      <section className="hp-section hp-modules-section">
        <div className="hp-section-head">
          <div className="hp-section-tag">Platform Modules</div>
          <h2 className="hp-section-h2">Six Integrated Capabilities</h2>
          <p className="hp-section-p">
            Each module is independently actionable and shares a common data pipeline.
          </p>
        </div>
        <div className="hp-modules-grid">
          {MODULES.map((m) => (
            <button key={m.num} className="hp-module-card" onClick={() => onNavigate(m.page)}>
              <div className="hp-module-head">
                <div className="hp-module-icon">{m.icon}</div>
                <div className="hp-module-num">{m.num}</div>
              </div>
              <div className="hp-module-title">{m.title}</div>
              <div className="hp-module-desc">{m.desc}</div>
              <div className="hp-module-link">
                Open module
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" width="10" height="10">
                  <path d="M2 6h8M6 2l4 4-4 4"/>
                </svg>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* ── Pipeline strip ───────────────────────────── */}
      <section className="hp-pipeline-section">
        <div className="hp-section-head hp-section-head-center">
          <div className="hp-section-tag">Methodology</div>
          <h2 className="hp-section-h2">End-to-End Data Pipeline</h2>
          <p className="hp-section-p">From raw challan records to ranked enforcement dispatch in four stages.</p>
        </div>
        <div className="hp-pipeline">
          {PIPELINE.map((p, i) => (
            <div key={p.step} className="hp-pipe-step">
              <div className="hp-pipe-connector">
                <div className="hp-pipe-node">
                  <span>{String(i + 1).padStart(2, '0')}</span>
                </div>
                {i < PIPELINE.length - 1 && <div className="hp-pipe-line" />}
              </div>
              <div className="hp-pipe-step-tag">{p.step}</div>
              <div className="hp-pipe-title">{p.title}</div>
              <div className="hp-pipe-body">{p.body}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA band ─────────────────────────────────── */}
      <section className="hp-cta-band">
        <div className="hp-cta-inner">
          <div className="hp-cta-left">
            <div className="hp-cta-label">Ready to operate</div>
            <div className="hp-cta-title">Open the Operations Dashboard</div>
            <div className="hp-cta-sub">Models loaded · Data current · 132 junctions indexed</div>
          </div>
          <div className="hp-cta-actions">
            <button className="hp-btn-primary hp-btn-primary-lg" onClick={() => onNavigate('prediction')}>
              Launch Dashboard
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                <path d="M3 8h10M9 4l4 4-4 4"/>
              </svg>
            </button>
            <button className="hp-btn-ghost hp-btn-ghost-light" onClick={() => onNavigate('pis')}>
              View Impact Scores
            </button>
          </div>
        </div>
      </section>

    </div>
  );
}
