import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Loader2 } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts';
import { scoreKey, toDatetimeLocalValue } from '../utils/colorUtils';
import './ForecastPanel.css';

const HORIZONS = [1, 2, 4, 8, 24];
const LINE_COLORS = ['#ef4444', '#f59e0b', '#f97316', '#3b82f6', '#8b5cf6'];

function addHours(tsLocal, h) {
  const d = new Date(tsLocal);
  d.setHours(d.getHours() + h);
  return toDatetimeLocalValue(d);
}

const BADGE_META = {
  Rising: { cls: 'fp-badge-rising', icon: '↑' },
  Easing:  { cls: 'fp-badge-easing', icon: '↓' },
  Stable:  { cls: 'fp-badge-stable', icon: '→' },
};

const ForecastPanel = ({ baseTimestamp, apiBase, selectedModel, topLocations, onForecastData }) => {
  const [chartData, setChartData] = useState([]);
  const [badges, setBadges]       = useState({});
  const [loading, setLoading]     = useState(false);
  const key = scoreKey(selectedModel);

  // Stable dep key — avoid re-fetching on every render
  const locKey = topLocations?.slice(0, 5).map(l => l.location_key).join('|') || '';
  const prevLocKey = useRef('');
  const prevTs     = useRef('');

  useEffect(() => {
    if (!baseTimestamp || !locKey) return;
    if (baseTimestamp === prevTs.current && locKey === prevLocKey.current) return;
    prevTs.current     = baseTimestamp;
    prevLocKey.current = locKey;

    const top5 = topLocations.slice(0, 5);
    setLoading(true);

    Promise.all(
      HORIZONS.map(h => {
        const ts = addHours(baseTimestamp, h);
        return axios
          .get(`${apiBase}/predict?timestamp=${encodeURIComponent(ts)}&top_n=50`, { timeout: 30000 })
          .then(r => ({ hour: `+${h}h`, results: r.data || [] }))
          .catch(() => ({ hour: `+${h}h`, results: [] }));
      })
    ).then(horizonResults => {
      const data = horizonResults.map(({ hour, results }) => {
        const point = { hour };
        top5.forEach(loc => {
          const match = results.find(r => r.location_key === loc.location_key);
          point[loc.location_key] = match ? (match[key] || 0) : 0;
        });
        return point;
      });

      setChartData(data);

      const newBadges = {};
      top5.forEach(loc => {
        const t1  = data[0]?.[loc.location_key]  || 0;
        const t24 = data[data.length - 1]?.[loc.location_key] || 0;
        const change = t1 > 0 ? (t24 - t1) / t1 : 0;
        newBadges[loc.location_key] =
          change > 0.2 ? 'Rising' : change < -0.2 ? 'Easing' : 'Stable';
      });
      setBadges(newBadges);

      if (onForecastData) onForecastData({ chartData: data, locations: top5 });
    }).finally(() => setLoading(false));
  }, [baseTimestamp, locKey]);

  const top5 = topLocations?.slice(0, 5) || [];
  const activeLines = top5.filter(loc => chartData.some(d => d[loc.location_key] > 0));

  return (
    <div className="forecast-panel">
      <div className="fp-header">
        <span className="fp-title">24-Hour Forecast — Top 5 Hotspots</span>
        {!loading && Object.keys(badges).length > 0 && (
          <div className="fp-badge-row">
            {top5.map((loc, i) => {
              const badge = badges[loc.location_key];
              if (!badge) return null;
              const { cls, icon } = BADGE_META[badge] || BADGE_META.Stable;
              return (
                <span key={loc.location_key} className={`fp-badge ${cls}`} style={{ borderColor: LINE_COLORS[i] }}>
                  {icon} {loc.location_key.replace(/^[A-Z0-9]+ - /, '')} — {badge}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {loading ? (
        <div className="fp-loading">
          <div className="fp-skeleton" />
          <div className="fp-skeleton fp-skeleton-sm" />
          <div className="fp-skeleton fp-skeleton-xs" />
          <div className="fp-loading-label">
            <Loader2 size={14} className="spin-icon" />
            Fetching 5-horizon forecast…
          </div>
        </div>
      ) : chartData.length === 0 ? (
        <div className="fp-empty">Run a prediction first to generate the 24h forecast.</div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: -20, bottom: 0 }}>
            <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip
              formatter={(val, name) => {
                const loc = top5.find(l => l.location_key === name);
                const label = loc ? loc.location_key.replace(/^[A-Z0-9]+ - /, '') : name;
                return [val.toFixed(2), label];
              }}
            />
            <Legend
              formatter={name => {
                const loc = top5.find(l => l.location_key === name);
                return loc ? loc.location_key.replace(/^[A-Z0-9]+ - /, '') : name;
              }}
              wrapperStyle={{ fontSize: 10 }}
            />
            {activeLines.map((loc, i) => (
              <Line
                key={loc.location_key}
                type="monotone"
                dataKey={loc.location_key}
                stroke={LINE_COLORS[i % LINE_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
};

export default ForecastPanel;
