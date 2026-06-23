import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

// Use environment variable for production, otherwise relative paths (proxied by Vite dev server)
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const API_BASE = `${BASE_URL}/api/v1`;
export const SEV_API  = `${BASE_URL}/api/v1/traffic-severity`;

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

  const runPrediction = useCallback(async (timestamp, endpoint = API_BASE) => {
    setLoading(true);
    setError(null);
    try {
      const url = `${endpoint}/predict?timestamp=${encodeURIComponent(timestamp)}`;
      const res = await axios.get(url, { timeout: 90000 });
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
