import React from 'react';
import { Users, Radio, TrendingUp, MapPin } from 'lucide-react';
import { OFFICER_COLORS } from './DeploymentMap';
import './DeploymentSidebar.css';

const DeploymentSidebar = ({
  officerCount, setOfficerCount,
  patrolRadius, setPatrolRadius,
  deployment,
  extraClassName,
}) => {
  const hasPredictions = deployment && deployment.active.length > 0;
  const pct    = deployment ? deployment.coveragePct : 0;
  const gainPct = deployment ? deployment.nextBestGainPct : 0;
  const coveredHotspots = deployment
    ? deployment.assignments.reduce((s, a) => s + a.covered.length, 0)
    : 0;
  const officersDeployed = deployment ? deployment.officersUsed : 0;
  const interceptedViol = deployment
    ? deployment.assignments.reduce((s, a) =>
        s + a.covered.reduce((ss, p) => ss + (p.naive_prediction || p.baseline_prediction || 0), 0), 0)
    : 0;

  return (
    <aside className={`deployment-sidebar${extraClassName ? ` ${extraClassName}` : ''}`}>
      <div className="ds-header">
        <div className="ds-header-title">
          <Users size={18} className="ds-header-icon" />
          <h2>Deployment Optimizer</h2>
        </div>
      </div>

      <div className="ds-body">

        {/* ── Officer count slider ─── */}
        <section className="ds-section">
          <div className="ds-section-label">
            <Users size={14} />
            Officers Available
            <span className="ds-section-val">{officerCount}</span>
          </div>
          <input
            type="range"
            className="ds-slider ds-slider-blue"
            min={1} max={50} step={1}
            value={officerCount}
            style={{ '--pct': `${((officerCount - 1) / 49) * 100}%` }}
            onChange={e => setOfficerCount(Number(e.target.value))}
          />
          <div className="ds-slider-range"><span>1</span><span>50</span></div>
        </section>

        {/* ── Patrol radius slider ─── */}
        <section className="ds-section">
          <div className="ds-section-label">
            <Radio size={14} />
            Patrol Radius
            <span className="ds-section-val">{patrolRadius >= 1000 ? `${(patrolRadius / 1000).toFixed(1)} km` : `${patrolRadius} m`}</span>
          </div>
          <input
            type="range"
            className="ds-slider ds-slider-blue"
            min={200} max={2000} step={100}
            value={patrolRadius}
            style={{ '--pct': `${((patrolRadius - 200) / 1800) * 100}%` }}
            onChange={e => setPatrolRadius(Number(e.target.value))}
          />
          <div className="ds-slider-range"><span>200 m</span><span>2 km</span></div>
        </section>

        {/* ── Coverage metrics ─── */}
        <section className="ds-metrics-section">
          <div className="ds-metrics-header">
            <TrendingUp size={14} />
            Coverage Metrics
          </div>

          {!hasPredictions ? (
            <div className="ds-empty">Run a prediction to see deployment metrics</div>
          ) : (
            <>
              <div className="ds-coverage-bar-wrap">
                <div className="ds-coverage-bar-label">
                  <span>Severity score covered</span>
                  <strong>{pct.toFixed(1)}%</strong>
                </div>
                <div className="ds-coverage-track">
                  <div
                    className="ds-coverage-fill"
                    style={{ width: `${Math.min(pct, 100)}%` }}
                  />
                </div>
              </div>

              <div className="ds-stats-grid">
                <div className="ds-stat-box">
                  <span className="ds-stat-num">{officersDeployed}</span>
                  <span className="ds-stat-lbl">Officers<br/>deployed</span>
                </div>
                <div className="ds-stat-box">
                  <span className="ds-stat-num">{coveredHotspots}</span>
                  <span className="ds-stat-lbl">Hotspots<br/>covered</span>
                </div>
                <div className="ds-stat-box">
                  <span className="ds-stat-num">{interceptedViol.toFixed(0)}</span>
                  <span className="ds-stat-lbl">Viol/hr<br/>intercepted</span>
                </div>
              </div>
            </>
          )}
        </section>

        {/* ── Next best deployment ─── */}
        {hasPredictions && deployment.nextBest && (
          <section className="ds-next-best">
            <div className="ds-next-best-label">
              <MapPin size={13} />
              Next Best Deployment
            </div>
            <div className="ds-next-best-card">
              <div className="ds-next-best-officer">
                Officer {deployment.assignments.length + 1}
              </div>
              <div className="ds-next-best-loc">
                {deployment.nextBest.location_key}
              </div>
              <div className="ds-next-best-area">
                {deployment.nextBest.area || deployment.nextBest.police_station || '—'}
              </div>
              <div className="ds-next-best-gain">
                +{gainPct.toFixed(1)}% more coverage
              </div>
            </div>
          </section>
        )}

        {/* ── Officer assignments ─── */}
        {hasPredictions && deployment.assignments.length > 0 && (
          <section className="ds-assignments">
            <div className="ds-assignments-header">Officer Assignments</div>
            <div className="ds-assignment-list">
              {deployment.assignments.map((a, i) => {
                const color = OFFICER_COLORS[i % OFFICER_COLORS.length];
                const multi = a.officerCount > 1;
                const endNum = a.startNum + a.officerCount - 1;
                const label = multi ? `${a.startNum}–${endNum}` : `${a.startNum}`;
                return (
                  <div key={a.startNum} className="ds-assignment-row">
                    <div className="ds-officer-badge-wrap">
                      <div
                        className="ds-officer-badge"
                        style={{ background: color }}
                      >
                        {label}
                      </div>
                      {multi && (
                        <span className="ds-officer-multi" style={{ color }}>×{a.officerCount}</span>
                      )}
                    </div>
                    <div className="ds-assignment-info">
                      <div className="ds-assignment-loc">
                        {a.location.location_key.replace(/^[A-Z0-9]+ - /, '')}
                      </div>
                      <div className="ds-assignment-meta">
                        {a.covered.length} hotspots · score {a.coveredScore.toFixed(1)}
                        {multi && <span className="ds-assignment-reinforce"> · high congestion</span>}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>

      <div className="ds-footer">
        <span>Greedy max-coverage</span>
        <span className="ds-footer-live">● Active</span>
      </div>
    </aside>
  );
};

export default DeploymentSidebar;
