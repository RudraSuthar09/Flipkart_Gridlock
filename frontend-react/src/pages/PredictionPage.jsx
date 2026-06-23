import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, Map, SlidersHorizontal, AlertTriangle } from 'lucide-react';
import { useApiHealth, usePredictions, API_BASE } from '../hooks/useApi';
import { toDatetimeLocalValue } from '../utils/colorUtils';
import HeatMap from '../components/HeatMap';
import ControlsSidebar from '../components/ControlsSidebar';
import EnforcementSidebar from '../components/EnforcementSidebar';
import './PageLayout.css';

const DISPLAY_TOP_N = 3200;

const PredictionPage = ({ onPredictionsLoaded }) => {
  const { health, status: apiStatus } = useApiHealth();
  const { predictions, loading, error, runPrediction } = usePredictions();
  const [selectedModel, setSelectedModel] = useState('lightgbm');
  const [timestamp, setTimestamp] = useState('');
  // null = map only (default), 'controls' = left sidebar open, 'enforcement' = right sidebar open
  const [mobileSidebar, setMobileSidebar] = useState(null);

  useEffect(() => {
    if (health?.panel_last_updated) {
      const panelEnd = new Date(health.panel_last_updated.replace(' ', 'T'));
      panelEnd.setMinutes(0, 0, 0);
      setTimestamp(toDatetimeLocalValue(panelEnd));
    }
  }, [health]);

  useEffect(() => {
    if (onPredictionsLoaded) onPredictionsLoaded(predictions);
  }, [predictions, onPredictionsLoaded]);

  const handleRun = useCallback(async () => {
    if (!timestamp) return alert('Please pick a target date & hour first.');
    await runPrediction(timestamp, API_BASE);
  }, [timestamp, runPrediction]);

  const toggleMobile = (panel) =>
    setMobileSidebar(prev => prev === panel ? null : panel);

  const statusDot = apiStatus === 'ok'
    ? { color: '#22c55e', label: health ? `API ready · ${health.location_count?.toLocaleString()} locations` : 'API ready' }
    : apiStatus === 'loading'
    ? { color: '#f59e0b', label: 'Connecting to API…' }
    : { color: '#ef4444', label: 'Cannot reach API (port 8001)' };

  return (
    <div className="page-layout">
      {/* Backdrop closes sidebar on mobile */}
      {mobileSidebar && (
        <div className="mobile-sidebar-backdrop" onClick={() => setMobileSidebar(null)} />
      )}

      <ControlsSidebar
        title="Count Heatmap"
        subtitle="How many violations are predicted"
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
        predictions={predictions}
        scoreColor="indigo"
        legend={{
          lo: 'Low Risk',
          hi: 'High Risk',
          gradient: 'linear-gradient(to right, #22c55e, #f59e0b, #ef4444)',
        }}
        displayTopN={DISPLAY_TOP_N}
        extraClassName={mobileSidebar === 'controls' ? 'mobile-open' : ''}
      />

      <div className="map-section">
        <HeatMap
          predictions={predictions}
          selectedModel={selectedModel}
          colorScheme="count"
          displayTopN={DISPLAY_TOP_N}
        />

        {/* Plain-language mode explanation — helps non-technical users */}
        <div className="map-mode-card">
          <div className="map-mode-card-icon">🔢</div>
          <div className="map-mode-card-title">Violation Count View</div>
          <p className="map-mode-card-desc">
            Shows <strong>where</strong> illegal parking happens most often.
            Larger & redder = more violations predicted this hour.
          </p>
        </div>

        {loading && (
          <div className="map-loading-overlay">
            <Loader2 className="spin-icon" size={32} />
            <p>Fetching predictions…</p>
          </div>
        )}
      </div>

      <EnforcementSidebar
        predictions={predictions}
        selectedModel={selectedModel}
        colorScheme="count"
        showSeverityFields={false}
        extraClassName={mobileSidebar === 'enforcement' ? 'mobile-open' : ''}
      />

      {/* Mobile bottom tab bar */}
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
          className={`mobile-tab-btn ${mobileSidebar === 'enforcement' ? 'active' : ''}`}
          onClick={() => toggleMobile('enforcement')}
        >
          <AlertTriangle size={20} />
          Alerts
        </button>
      </div>
    </div>
  );
};

export default PredictionPage;
