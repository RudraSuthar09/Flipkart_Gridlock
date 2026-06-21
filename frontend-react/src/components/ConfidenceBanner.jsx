import React from 'react';
import './ConfidenceBanner.css';

const ConfidenceBanner = ({ health }) => {
  if (!health) return null;
  const vCov = Math.round((health.vehicle_mapping_coverage || 0) * 100);
  const lCov = Math.round((health.lane_match_coverage || 0) * 100);
  const allGood = vCov >= 95 && lCov >= 95;

  return (
    <div className={`confidence-banner ${allGood ? 'banner-ok' : 'banner-warn'}`}>
      <span className="cb-icon">{allGood ? '✓' : '⚠'}</span>
      <span>
        Vehicle type known for <strong>{vCov}%</strong> of violations ·{' '}
        Lane data matched for <strong>{lCov}%</strong> of locations
      </span>
    </div>
  );
};

export default ConfidenceBanner;
