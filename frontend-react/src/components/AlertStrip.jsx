import React, { useState, useMemo } from 'react';
import './AlertStrip.css';

const AlertStrip = ({ forecastData }) => {
  const [dismissed, setDismissed] = useState(new Set());

  const alerts = useMemo(() => {
    if (!forecastData?.chartData?.length || !forecastData?.locations?.length) return [];

    const { chartData, locations } = forecastData;
    const t1Point = chartData[0];
    const rawAlerts = [];

    locations.forEach(loc => {
      const t1Score = t1Point?.[loc.location_key] || 0;

      chartData.slice(1).forEach(point => {
        const score = point[loc.location_key] || 0;
        if (score > 1.5 * t1Score && score > 2.0) {
          rawAlerts.push({
            id: `${loc.location_key}-${point.hour}`,
            location: loc.location_key,
            locationName: loc.location_key.replace(/^[A-Z0-9]+ - /, ''),
            hour: point.hour,
            score,
            baseScore: t1Score,
            magnitude: score - t1Score,
          });
        }
      });
    });

    return rawAlerts.sort((a, b) => b.magnitude - a.magnitude).slice(0, 5);
  }, [forecastData]);

  const visible = alerts.filter(a => !dismissed.has(a.id));
  if (visible.length === 0) return null;

  const dismiss = (id) => setDismissed(s => new Set([...s, id]));

  return (
    <div className="alert-strip">
      {visible.map((alert, i) => (
        <div key={alert.id} className={`alert-card ${i === 0 ? 'alert-card-top' : ''}`}>
          <span className="alert-icon">⚠</span>
          <div className="alert-content">
            <span className="alert-location">{alert.locationName}</span>
            <span className="alert-detail">
              spike at {alert.hour} · score {alert.score.toFixed(1)}
            </span>
          </div>
          <button className="alert-dismiss" onClick={() => dismiss(alert.id)} title="Dismiss">×</button>
        </div>
      ))}
    </div>
  );
};

export default AlertStrip;
