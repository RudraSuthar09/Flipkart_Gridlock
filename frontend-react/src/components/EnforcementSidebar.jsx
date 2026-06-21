import React from 'react';
import { MoreVertical, Eye, Filter } from 'lucide-react';
import { scoreKey, riskColor, sevRiskColor, VEH_SHORT } from '../utils/colorUtils';
import './EnforcementSidebar.css';

const SEVERITY_TAGS = ['CRITICAL', 'ELEVATED', 'MONITORING'];

const EnforcementSidebar = ({ predictions, selectedModel, colorScheme, showSeverityFields }) => {
  const key = scoreKey(selectedModel);
  const colorFn = colorScheme === 'severity' ? sevRiskColor : riskColor;

  const sorted = [...predictions].sort((a, b) => (b[key] || 0) - (a[key] || 0));
  const top3 = sorted.slice(0, 3);

  // Use max from the full predictions set as baseline
  const allScores = predictions.map(p => p[key] || 0);
  const globalMax = allScores.length ? Math.max(...allScores) : 1;
  const effectiveMax = Math.max(globalMax, 1e-6);

  const getTags = idx => ({
    label: SEVERITY_TAGS[idx] || 'MONITORING',
    cls: ['tag-critical', 'tag-elevated', 'tag-monitoring'][idx] || 'tag-monitoring',
  });

  const primaryColor = colorScheme === 'severity' ? '#f59e0b' : '#6366f1';

  return (
    <aside className="enforcement-sidebar">
      <div className="es-header">
        <h2>Enforcement</h2>
        <button className="icon-btn"><Filter size={18} /></button>
      </div>

      <div className="es-body">
        {top3.length === 0 ? (
          <div className="es-empty">
            <p>Run a prediction to see enforcement alerts</p>
          </div>
        ) : (
          top3.map((pred, idx) => {
            const { label: tagLabel, cls: tagCls } = getTags(idx);
            const score = pred[key] || 0;
            // Congestion % = score as % of global max (0–100)
            const congestionPct = Math.min(99, Math.round((score / effectiveMax) * 100));
            // Active violations = naive_prediction (raw count model) rounded to int
            const violations = Math.max(1, Math.round(pred.naive_prediction || pred.baseline_prediction || score));
            const color = colorFn(score / effectiveMax);

            return (
              <div key={pred.location_key} className="es-alert-card">
                <div className="es-card-header">
                  <span className={`es-tag ${tagCls}`}>{tagLabel}</span>
                  <button className="es-menu-btn"><MoreVertical size={15} /></button>
                </div>

                <h3 className="es-district">
                  District {String(idx + 1).padStart(2, '0')} — {pred.area || pred.police_station || 'Metro Hub'}
                </h3>

                <div className="es-stats-row">
                  <div className="es-stat">
                    <span className="es-stat-label">Congestion Impact</span>
                    <div className="es-stat-val">
                      <span className="es-icon-bars" style={{ color }}>▐▌▐</span>
                      {congestionPct}%
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
                  <div className="es-risk-fill" style={{ width: `${congestionPct}%`, background: color }} />
                </div>

                {idx === 0 && (
                  <div className="es-actions">
                    <button className="es-dispatch-btn" style={{ background: primaryColor }}>
                      Dispatch Unit
                    </button>
                    <button className="es-view-btn" style={{ background: primaryColor }}>
                      <Eye size={16} />
                    </button>
                  </div>
                )}

                {idx > 0 && (
                  <div className="es-meta">
                    <div className="es-meta-item">
                      <span className="es-meta-label">Location</span>
                      <span className="es-meta-val es-meta-trunc">
                        {pred.location_key.replace(/^[A-Z0-9]+ - /, '')}
                      </span>
                    </div>
                    <div className="es-meta-item">
                      <span className="es-meta-label">Raw Score</span>
                      <span className="es-meta-val">{score.toFixed(4)}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div className="es-footer">
        <span>System Status: Optimal</span>
        <span className="es-live">● Live sync</span>
      </div>
    </aside>
  );
};

export default EnforcementSidebar;
