import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { scoreKey, riskColor, sevRiskColor, VEH_SHORT } from '../utils/colorUtils';
import { getSeverityNarrative, getSeverityShortLabel } from '../utils/severityUtils';
import { highwayLabel } from '../utils/roadNameUtils';
import './EnforcementSidebar.css';

const SEVERITY_TAGS = ['CRITICAL', 'ELEVATED', 'MONITORING'];

export default function EnforcementSidebar({
  predictions, selectedModel, colorScheme, showSeverityFields,
  persistenceScores = {}, selectedStation = '',
  roadNames = {}, mostAffectedRoad = null, roadNamesLoading = false,
}) {
  const key     = scoreKey(selectedModel);
  const colorFn = colorScheme === 'severity' ? sevRiskColor : riskColor;
  const primary = colorScheme === 'severity' ? '#f59e0b' : '#6366f1';

  const [darkFleet,     setDarkFleet]     = useState([]);
  const [fleetOpen,     setFleetOpen]     = useState(false);
  const [fleetLoading,  setFleetLoading]  = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState(null);

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
        {showSeverityFields && (mostAffectedRoad || roadNamesLoading) && (
          <div className="es-most-affected-road">
            <div className="emar-label">
              <span className="emar-icon">🛣</span>
              Most Affected Road
            </div>
            {roadNamesLoading ? (
              <div className="emar-loading">Identifying roads…</div>
            ) : (
              <>
                <div className="emar-road-name">{mostAffectedRoad.name}</div>
                <div className="emar-meta">
                  {highwayLabel(mostAffectedRoad.highway)}
                  {' · '}
                  Affects {mostAffectedRoad.hotspotCount} of top-5 hotspots
                </div>
              </>
            )}
          </div>
        )}

        {top10.length === 0 ? (
          <div className="es-empty">
            <p>Run a prediction to see enforcement alerts</p>
          </div>
        ) : (
          <>
            {/* Top 3 full alert cards */}
            {top10.slice(0, 3).map((pred, idx) => {
              const { label: tagLabel, cls: tagCls } = getTags(idx);
              const score      = pred[key] || 0;
              const pct        = Math.min(99, Math.round((score / globalMax) * 100));
              const violations = Math.max(1, Math.round(pred.naive_prediction || pred.baseline_prediction || 1));
              const color      = colorFn(score / globalMax);
              const badge      = getBadge(pred);
              const name       = pred.location_key.replace(/^[A-Z0-9]+ - /, '');
              const lat        = pred.latitude;
              const lon        = pred.longitude;

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

                  {showSeverityFields && (() => {
                    const { headline, detail, blockagePct } = getSeverityNarrative(pred);
                    const barColor = blockagePct >= 80 ? '#ef4444' : blockagePct >= 50 ? '#f59e0b' : '#22c55e';
                    return (
                      <div className="es-severity-reason">
                        <div className="es-severity-headline">{headline}</div>
                        <div className="es-severity-detail">{detail}</div>
                        <div className="es-severity-bar-wrap">
                          <div className="es-severity-bar-track">
                            <div
                              className="es-severity-bar-fill"
                              style={{ width: `${blockagePct}%`, background: barColor }}
                            />
                          </div>
                          <span className="es-severity-bar-label">{blockagePct}% carriageway</span>
                        </div>
                      </div>
                    );
                  })()}

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

                  {showSeverityFields && (() => {
                    const locRoads = roadNames[pred.location_key] || [];
                    if (!locRoads.length) return null;
                    return (
                      <div className="es-road-names">
                        <div className="es-rn-header">Affected Roads</div>
                        {locRoads.map((r, i) => (
                          <div key={r.name} className={`es-rn-row${i === 0 ? ' es-rn-primary' : ''}`}>
                            <span className="es-rn-dot" />
                            <span className="es-rn-name">{r.name}</span>
                            <span className="es-rn-hw">{highwayLabel(r.highway)}</span>
                          </div>
                        ))}
                      </div>
                    );
                  })()}

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
                          {showSeverityFields && (() => {
                            const roads = roadNames[pred.location_key];
                            return roads?.[0]
                              ? <span className="es-compact-road">{roads[0].name}</span>
                              : null;
                          })()}
                          {showSeverityFields && pred.dominant_vehicle_cat && (
                            <span className="es-compact-severity-sub">
                              {getSeverityShortLabel(pred)}
                            </span>
                          )}
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
