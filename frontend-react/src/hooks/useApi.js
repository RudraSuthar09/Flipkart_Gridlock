import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { loadPOIs, enrichPredictionsWithZones } from '../utils/proximityUtils.js';

// Use relative paths — proxied by Vite dev server to http://127.0.0.1:8001
export const API_BASE = '/api/v1';
export const SEV_API  = '/api/v1/traffic-severity';

export function useApiHealth() {
  const [health, setHealth] = useState(null);
  const [sevHealth, setSevHealth] = useState(null);
  const [status, setStatus] = useState('loading'); // 'loading' | 'ok' | 'error'

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const [r1, r2] = await Promise.all([
          axios.get(`${API_BASE}/health`, { timeout: 8000 }),
          axios.get(`${SEV_API}/health`, { timeout: 8000 }),
        ]);
        setHealth(r1.data);
        setSevHealth(r2.data);
        setStatus('ok');
      } catch {
        setStatus('error');
      }
    };
    fetchHealth();
  }, []);

  return { health, sevHealth, status };
}

export function usePredictions() {
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // ── Pre-load OSM POIs on mount ─────────────────────────────────
  // LOGIC: We kick off the POI fetch as soon as the component mounts,
  // in the background. By the time the user clicks "Run Prediction",
  // the POIs will almost certainly already be in memory — zone enrichment
  // after prediction fetch will then be instant.
  useEffect(() => {
    loadPOIs().catch(() => {}); // Silently ignore if POI file not ready
  }, []);

  const runPrediction = useCallback(async (timestamp, endpoint = API_BASE) => {
    setLoading(true);
    setError(null);
    try {
      const url = `${endpoint}/predict?timestamp=${encodeURIComponent(timestamp)}`;
      const res = await axios.get(url, { timeout: 90000 });

      // ── OSM Zone Enrichment ──────────────────────────────────────
      // LOGIC: After predictions arrive from the API, we call
      // enrichPredictionsWithZones() which iterates every prediction,
      // runs the spatial index proximity check, and stamps a `.zone`
      // property on each prediction object (in-place mutation).
      // This is non-fatal — if it fails, raw predictions still work.
      try {
        await loadPOIs();                        // no-op if already loaded
        enrichPredictionsWithZones(res.data);    // stamps .zone on each prediction
      } catch (zoneErr) {
        console.warn('[OSM] Zone enrichment skipped:', zoneErr.message);
      }

      setPredictions(res.data);
      return res.data;
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || 'Unknown error';
      setError(msg);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  return { predictions, loading, error, runPrediction };
}
