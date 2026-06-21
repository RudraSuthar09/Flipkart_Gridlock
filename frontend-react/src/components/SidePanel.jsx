import React from 'react';
import { MoreVertical, Filter, Eye } from 'lucide-react';
import './SidePanel.css';

const getSeverityTag = (index) => {
  if (index === 0) return { label: 'CRITICAL', className: 'tag-critical' };
  if (index === 1) return { label: 'ELEVATED', className: 'tag-elevated' };
  return { label: 'MONITORING', className: 'tag-monitoring' };
};

const SidePanel = ({ predictions }) => {
  // Take top 3 for the demo view based on the image
  const displayItems = predictions.slice(0, 3);

  return (
    <aside className="sidepanel">
      <div className="sidepanel-header">
        <h2>Enforcement</h2>
        <button className="icon-btn">
          <Filter size={18} />
        </button>
      </div>
      
      <div className="sidepanel-content">
        {displayItems.length === 0 ? (
          <div className="empty-state">No predictions available</div>
        ) : (
          displayItems.map((pred, idx) => {
            const tag = getSeverityTag(idx);
            return (
              <div key={pred.location_key} className="alert-card">
                <div className="card-header">
                  <span className={`severity-tag ${tag.className}`}>{tag.label}</span>
                  <button className="card-menu-btn"><MoreVertical size={16} /></button>
                </div>
                
                <h3 className="district-title">District {(idx + 1).toString().padStart(2, '0')} - {pred.area || 'Metro Hub'}</h3>
                
                <div className="card-stats">
                  <div className="stat-group">
                    <span className="stat-label">Congestion Impact</span>
                    <div className="stat-value">
                      <span className="stat-icon bars"></span>
                      {Math.round(pred.lightgbm_prediction * 1000) || (85 - idx * 23)}%
                    </div>
                  </div>
                  <div className="stat-group">
                    <span className="stat-label">Active Violations</span>
                    <div className="stat-value">
                      <span className="stat-icon parking">P</span>
                      {Math.round(pred.baseline_prediction * 100) || (12 - idx * 4)}
                    </div>
                  </div>
                </div>

                {idx === 0 && (
                  <div className="card-actions">
                    <button className="btn-dispatch">Dispatch Unit</button>
                    <button className="btn-view"><Eye size={18} /></button>
                  </div>
                )}

                {idx > 0 && (
                  <div className="card-meta">
                    <div className="meta-group">
                      <span className="meta-label">Report ID:</span>
                      <span className="meta-value">2023-A00{idx}</span>
                    </div>
                    <div className="meta-group">
                      <span className="meta-label">Timestamp:</span>
                      <span className="meta-value">10/26/2023, 14:30</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div className="sidepanel-footer">
        <span className="system-status">System Status: Optimal</span>
        <span className="live-sync">Live sync</span>
      </div>
    </aside>
  );
};

export default SidePanel;
