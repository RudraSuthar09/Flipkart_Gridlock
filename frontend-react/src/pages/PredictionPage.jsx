import React, { useState, useEffect, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
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

  // Set default timestamp from panel_last_updated so scores are in-range
  useEffect(() => {
    if (health?.panel_last_updated) {
      const panelEnd = new Date(health.panel_last_updated.replace(' ', 'T'));
      panelEnd.setMinutes(0, 0, 0);
      setTimestamp(toDatetimeLocalValue(panelEnd));
    }
  }, [health]);

  // Expose predictions to parent for chatbot
  useEffect(() => {
    if (onPredictionsLoaded) onPredictionsLoaded(predictions);
  }, [predictions, onPredictionsLoaded]);

  const handleRun = useCallback(async () => {
    if (!timestamp) return alert('Please pick a target date & hour first.');
    await runPrediction(timestamp, API_BASE);
  }, [timestamp, runPrediction]);

  const statusDot = apiStatus === 'ok'
    ? { color: '#22c55e', label: health ? `API ready · ${health.location_count?.toLocaleString()} locations` : 'API ready' }
    : apiStatus === 'loading'
    ? { color: '#f59e0b', label: 'Connecting to API…' }
    : { color: '#ef4444', label: 'Cannot reach API (port 8001)' };

  return (
    <div className="page-layout">
      <ControlsSidebar
        title="Count Heatmap"
        subtitle="Violation risk forecast"
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
      />

      <div className="map-section">
        <HeatMap
          predictions={predictions}
          selectedModel={selectedModel}
          colorScheme="count"
          displayTopN={DISPLAY_TOP_N}
        />
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
      />
    </div>
  );
};

export default PredictionPage;
