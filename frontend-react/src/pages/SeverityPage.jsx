import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, Map, SlidersHorizontal, AlertTriangle } from 'lucide-react';
import { useApiHealth, usePredictions, SEV_API } from '../hooks/useApi';
import { toDatetimeLocalValue } from '../utils/colorUtils';
import HeatMap from '../components/HeatMap';
import ControlsSidebar from '../components/ControlsSidebar';
import EnforcementSidebar from '../components/EnforcementSidebar';
import ConfidenceBanner from '../components/ConfidenceBanner';
import './PageLayout.css';

const DISPLAY_TOP_N = 3200;

const SeverityPage = ({ onPredictionsLoaded }) => {
  const { sevHealth, status: apiStatus } = useApiHealth();
  const { predictions, loading, error, runPrediction } = usePredictions();
  const [selectedModel, setSelectedModel] = useState('lightgbm');
  const [timestamp, setTimestamp] = useState('');
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

  const handleRun = useCallback(async () => {
    if (!timestamp) return alert('Please pick a target date & hour first.');
    await runPrediction(timestamp, SEV_API);
  }, [timestamp, runPrediction]);

  const toggleMobile = (panel) =>
    setMobileSidebar(prev => prev === panel ? null : panel);

  const statusDot = apiStatus === 'ok'
    ? { color: '#22c55e', label: sevHealth ? `API ready · ${sevHealth.location_count?.toLocaleString()} locations` : 'API ready' }
    : apiStatus === 'loading'
    ? { color: '#f59e0b', label: 'Connecting to severity API…' }
    : { color: '#ef4444', label: 'Cannot reach API (port 8001)' };

  return (
    <div className="page-layout">
      {mobileSidebar && (
        <div className="mobile-sidebar-backdrop" onClick={() => setMobileSidebar(null)} />
      )}

      <ControlsSidebar
        title="Severity Heatmap"
        subtitle="How badly violations block traffic"
        icon="severity"
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
        extraContent={sevHealth && <ConfidenceBanner health={sevHealth} />}
        extraClassName={mobileSidebar === 'controls' ? 'mobile-open' : ''}
      />

      <div className="map-section">
        <HeatMap
          predictions={predictions}
          selectedModel={selectedModel}
          colorScheme="severity"
          displayTopN={DISPLAY_TOP_N}
        />

        {/* Plain-language mode explanation */}
        <div className="map-mode-card">
          <div className="map-mode-card-icon">⚠️</div>
          <div className="map-mode-card-title">Traffic Impact View</div>
          <p className="map-mode-card-desc">
            Shows <strong>how badly</strong> parking blocks traffic — based on road type,
            vehicle size &amp; lane count. Red = worst congestion impact.
          </p>
        </div>

        {loading && (
          <div className="map-loading-overlay">
            <Loader2 className="spin-icon" size={32} />
            <p>Fetching severity predictions…</p>
          </div>
        )}
      </div>

      <EnforcementSidebar
        predictions={predictions}
        selectedModel={selectedModel}
        colorScheme="severity"
        showSeverityFields={true}
        extraClassName={mobileSidebar === 'enforcement' ? 'mobile-open' : ''}
      />

      {/* Mobile bottom tab bar */}
      <div className="mobile-tab-bar">
        <button
          className={`mobile-tab-btn sev ${mobileSidebar === 'controls' ? 'active' : ''}`}
          onClick={() => toggleMobile('controls')}
        >
          <SlidersHorizontal size={20} />
          Controls
        </button>
        <button
          className={`mobile-tab-btn sev ${mobileSidebar === null ? 'active' : ''}`}
          onClick={() => setMobileSidebar(null)}
        >
          <Map size={20} />
          Map
        </button>
        <button
          className={`mobile-tab-btn sev ${mobileSidebar === 'enforcement' ? 'active' : ''}`}
          onClick={() => toggleMobile('enforcement')}
        >
          <AlertTriangle size={20} />
          Alerts
        </button>
      </div>
    </div>
  );
};

export default SeverityPage;
