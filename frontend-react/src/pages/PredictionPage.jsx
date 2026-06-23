import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Loader2 } from 'lucide-react';
import { useApiHealth, usePredictions, API_BASE } from '../hooks/useApi';
import { toDatetimeLocalValue, scoreKey } from '../utils/colorUtils';
import HeatMap from '../components/HeatMap';
import ControlsSidebar from '../components/ControlsSidebar';
import EnforcementSidebar from '../components/EnforcementSidebar';
import ForecastPanel from '../components/ForecastPanel';
import AlertStrip from '../components/AlertStrip';
import './PageLayout.css';

const DISPLAY_TOP_N = 3200;

const PredictionPage = ({
  onPredictionsLoaded,
  searchQuery = '',
  selectedStation = '',
  onStationChange,
  persistenceScores = {},
}) => {
  const { health, status: apiStatus } = useApiHealth();
  const { predictions, loading, error, runPrediction } = usePredictions();
  const [selectedModel, setSelectedModel] = useState('lightgbm');
  const [timestamp, setTimestamp]         = useState('');
  const [showForecast, setShowForecast]   = useState(false);
  const [forecastData, setForecastData]   = useState(null);

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

  // Extract unique station options from predictions
  const stationOptions = useMemo(() => {
    const stations = [...new Set(predictions.map(p => p.police_station).filter(Boolean))];
    return stations.sort();
  }, [predictions]);

  // Apply search + station filter
  const filteredPredictions = useMemo(() => {
    let result = predictions;
    if (selectedStation) {
      result = result.filter(p => p.police_station === selectedStation);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(p =>
        p.location_key?.toLowerCase().includes(q) ||
        p.police_station?.toLowerCase().includes(q) ||
        p.area?.toLowerCase().includes(q)
      );
    }
    return result;
  }, [predictions, selectedStation, searchQuery]);

  const key  = scoreKey(selectedModel);
  const top5 = useMemo(() => (
    [...filteredPredictions].sort((a, b) => (b[key] || 0) - (a[key] || 0)).slice(0, 5)
  ), [filteredPredictions, key]);

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
        predictions={filteredPredictions}
        scoreColor="indigo"
        legend={{
          lo: 'Low Risk',
          hi: 'High Risk',
          gradient: 'linear-gradient(to right, #22c55e, #f59e0b, #ef4444)',
        }}
        displayTopN={DISPLAY_TOP_N}
        stationOptions={stationOptions}
        selectedStation={selectedStation}
        onStationChange={onStationChange}
        showForecast={showForecast}
        onForecastToggle={() => setShowForecast(v => !v)}
      />

      <div className="map-section">
        {forecastData && <AlertStrip forecastData={forecastData} />}
        <div className="map-inner">
          <HeatMap
            predictions={filteredPredictions}
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
        {showForecast && (
          <div className="forecast-drawer">
            <ForecastPanel
              baseTimestamp={timestamp}
              apiBase={API_BASE}
              selectedModel={selectedModel}
              topLocations={top5}
              onForecastData={setForecastData}
            />
          </div>
        )}
      </div>

      <EnforcementSidebar
        predictions={filteredPredictions}
        selectedModel={selectedModel}
        colorScheme="count"
        showSeverityFields={false}
        persistenceScores={persistenceScores}
        selectedStation={selectedStation}
      />
    </div>
  );
};

export default PredictionPage;
