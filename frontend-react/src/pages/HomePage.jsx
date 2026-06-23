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
    desc: 'Parallel multi-horizon predictions for T+1h, T+2h, T+4h, T+8h, and T+24h across the top 5 hotspots. Rising/Easing/Stable badges tell officers what\'s coming.',
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
