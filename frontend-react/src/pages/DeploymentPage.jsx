import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Loader2, Map, ShieldCheck, SlidersHorizontal, Users } from 'lucide-react';
import { useApiHealth, usePredictions, SEV_API } from '../hooks/useApi';
import { toDatetimeLocalValue, scoreKey } from '../utils/colorUtils';
import { computeDeployment } from '../utils/deploymentAlgo';
import ControlsSidebar from '../components/ControlsSidebar';
import DeploymentMap from '../components/DeploymentMap';
import DeploymentSidebar from '../components/DeploymentSidebar';
import './PageLayout.css';

const DISPLAY_TOP_N = 500;

const DeploymentPage = ({ onPredictionsLoaded }) => {
  const { sevHealth, status: apiStatus } = useApiHealth();
  const { predictions, loading, error, runPrediction } = usePredictions();
  const [selectedModel, setSelectedModel] = useState('lightgbm');
  const [timestamp, setTimestamp]         = useState('');
  const [officerCount, setOfficerCount]   = useState(5);
  const [patrolRadius, setPatrolRadius]   = useState(500);
  const [mobileSidebar, setMobileSidebar] = useState(null);

  useEffect(() => {
    if (sevHealth?.panel_last_updated) {
      const panelEnd = new Date(sevHealth.panel_last_updated.replace(' ', 'T'));
      panelEnd.setMinutes(0, 0, 0);
      setTimestamp(toDatetimeLocalValue(panelEnd));
    }
  }, [sevHealth]);

  useEffect(() => {
    if (onPredictionsLoaded) onPredictionsLoaded(predictions);
  }, [predictions, onPredictionsLoaded]);

  const sKey = scoreKey(selectedModel);

  const deployment = useMemo(() => {
    if (!predictions.length) return null;
    return computeDeployment(predictions, sKey, officerCount, patrolRadius);
  }, [predictions, sKey, officerCount, patrolRadius]);

  const handleRun = useCallback(async () => {
    if (!timestamp) return alert('Please pick a target date & hour first.');
    await runPrediction(timestamp, SEV_API);
  }, [timestamp, runPrediction]);

  const toggleMobile = (panel) =>
    setMobileSidebar(prev => prev === panel ? null : panel);

  const statusDot = apiStatus === 'ok'
    ? { color: '#22c55e', label: sevHealth ? `API ready · ${sevHealth.location_count?.toLocaleString()} locations` : 'API ready' }
    : apiStatus === 'loading'
    ? { color: '#f59e0b', label: 'Connecting to API…' }
    : { color: '#ef4444', label: 'Cannot reach API (port 8001)' };

  return (
    <div className="page-layout">
      {mobileSidebar && (
        <div className="mobile-sidebar-backdrop" onClick={() => setMobileSidebar(null)} />
      )}

      <ControlsSidebar
        title="Officer Deployment"
        subtitle="Greedy maximum-coverage optimizer"
        icon="deployment"
        statusColor={statusDot.color}
        statusLabel={statusDot.label}
        timestamp={timestamp}
        onTimestampChange={setTimestamp}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        onRun={handleRun}
        loading={loading}
        error={error}
        predictions={predictions}
        scoreColor="amber"
        legend={{
          lo: 'Low Severity',
          hi: 'High Severity',
          gradient: 'linear-gradient(to right, #10b981, #f59e0b, #ea580c, #dc2626)',
        }}
        displayTopN={DISPLAY_TOP_N}
        extraClassName={mobileSidebar === 'controls' ? 'mobile-open' : ''}
      />

      <div className="map-section">
        <DeploymentMap
          deployment={deployment}
          patrolRadius={patrolRadius}
          displayTopN={DISPLAY_TOP_N}
        />

        <div className="map-mode-card">
          <div className="map-mode-card-icon">
  <ShieldCheck size={24} />
</div>
          <div className="map-mode-card-title">Deployment Optimizer</div>
          <p className="map-mode-card-desc">
            Numbered pins = officer positions. Dashed circles = patrol coverage zones.
            Grey spots = not yet covered.
          </p>
        </div>

        {loading && (
          <div className="map-loading-overlay">
            <Loader2 className="spin-icon" size={32} />
            <p>Fetching severity predictions…</p>
          </div>
        )}
      </div>

      <DeploymentSidebar
        officerCount={officerCount}
        setOfficerCount={setOfficerCount}
        patrolRadius={patrolRadius}
        setPatrolRadius={setPatrolRadius}
        deployment={deployment}
        extraClassName={mobileSidebar === 'deployment' ? 'mobile-open' : ''}
      />

      <div className="mobile-tab-bar">
        <button
          className={`mobile-tab-btn ${mobileSidebar === 'controls' ? 'active' : ''}`}
          onClick={() => toggleMobile('controls')}
        >
          <SlidersHorizontal size={20} />
          Controls
        </button>
        <button
          className={`mobile-tab-btn ${mobileSidebar === null ? 'active' : ''}`}
          onClick={() => setMobileSidebar(null)}
        >
          <Map size={20} />
          Map
        </button>
        <button
          className={`mobile-tab-btn ${mobileSidebar === 'deployment' ? 'active' : ''}`}
          onClick={() => toggleMobile('deployment')}
        >
          <Users size={20} />
          Deploy
        </button>
      </div>
    </div>
  );
};

export default DeploymentPage;
