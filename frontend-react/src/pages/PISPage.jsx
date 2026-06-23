import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Loader2, ArrowUpDown, Flag, X } from 'lucide-react';
import axios from 'axios';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './PISPage.css';

const fmt = (n, d = 0) => (n == null ? '—' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: d }));
const fmtPct = (n) => (n == null ? '—' : `${(n * 100).toFixed(1)}%`);
const fmtInr = (n) => {
  if (n == null) return '—';
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  return `₹${Math.round(n).toLocaleString('en-IN')}`;
};

export default function PISPage() {
  const [pisData,       setPisData]       = useState([]);
  const [stationStats,  setStationStats]  = useState([]);
  const [pisLoading,    setPisLoading]    = useState(true);
  const [statLoading,   setStatLoading]   = useState(true);
  const [pisError,      setPisError]      = useState(null);
  const [activeTab,       setActiveTab]       = useState('pis');
  const [selectedJunction, setSelectedJunction] = useState(null);
  const [sortKey,         setSortKey]         = useState('pis_score');
  const [sortDir,       setSortDir]       = useState('desc');
  const [filterAction,  setFilterAction]  = useState('');

  useEffect(() => {
    axios.get('/api/v1/pis-scores', { timeout: 20000 })
      .then(r => setPisData((r.data || []).filter(row => !row.location_key?.startsWith('grid_'))))
      .catch(e => setPisError(e.message))
      .finally(() => setPisLoading(false));

    axios.get('/api/v1/station-stats', { timeout: 20000 })
      .then(r => setStationStats(r.data || []))
      .catch(() => {})
      .finally(() => setStatLoading(false));
  }, []);

  const handleSort = useCallback((k) => {
    setSortKey(prev => {
      if (prev === k) { setSortDir(d => d === 'asc' ? 'desc' : 'asc'); return k; }
      setSortDir('desc');
      return k;
    });
  }, []);

  const displayedPIS = [...pisData]
    .filter(r => !filterAction || r.action_type === filterAction)
    .sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      return sortDir === 'desc' ? bv - av : av - bv;
    });

  const [statSort,    setStatSort]    = useState('total_violations');
  const [statSortDir, setStatSortDir] = useState('desc');

  const displayedStats = [...stationStats].sort((a, b) => {
    const av = a[statSort] ?? 0;
    const bv = b[statSort] ?? 0;
    return statSortDir === 'desc' ? bv - av : av - bv;
  });

  const SortIcon = ({ k, activeK, dir }) => (
    <ArrowUpDown
      size={11}
      style={{ opacity: activeK === k ? 1 : 0.35, marginLeft: 3 }}
    />
  );

  return (
    <div className="pis-page" style={{ position: 'relative' }}>
      {/* Page header */}
      <div className="pis-header">
        <div>
          <h1 className="pis-title">Impact Scores</h1>
          <p className="pis-subtitle">
            Priority-ranked junctions by traffic disruption cost — ₹ loss/day, vehicle hours wasted, enforcement gap.
          </p>
        </div>

        <div className="pis-tabs">
          <button
            className={`pis-tab ${activeTab === 'pis' ? 'active' : ''}`}
            onClick={() => setActiveTab('pis')}
          >
            Junction Scores
            {pisData.length > 0 && <span className="pis-tab-count">{pisData.length}</span>}
          </button>
          <button
            className={`pis-tab ${activeTab === 'station' ? 'active' : ''}`}
            onClick={() => setActiveTab('station')}
          >
            Station Performance
            {stationStats.length > 0 && <span className="pis-tab-count">{stationStats.length}</span>}
          </button>
        </div>
      </div>

      {/* ── PIS Table ──────────────────────────────────────────────── */}
      {activeTab === 'pis' && (
        <div className="pis-content">
          {/* Filter bar */}
          <div className="pis-filter-bar">
            <button
              className={`pis-filter-btn ${filterAction === '' ? 'active' : ''}`}
              onClick={() => setFilterAction('')}
            >
              All
            </button>
            <button
              className={`pis-filter-btn intervene ${filterAction === 'Intervene' ? 'active' : ''}`}
              onClick={() => setFilterAction('Intervene')}
            >
              Intervene
            </button>
            <button
              className={`pis-filter-btn monitor ${filterAction === 'Monitor' ? 'active' : ''}`}
              onClick={() => setFilterAction('Monitor')}
            >
              Monitor
            </button>
            <span className="pis-filter-count">
              {displayedPIS.length} junctions
            </span>
          </div>

          {pisLoading ? (
            <div className="pis-loading"><Loader2 size={24} className="spin-icon" /><p>Loading impact scores…</p></div>
          ) : pisError ? (
            <div className="pis-error">⚠ {pisError}</div>
          ) : displayedPIS.length === 0 ? (
            <div className="pis-empty">No data available. Ensure the backend is running.</div>
          ) : (
            <div className="pis-table-wrap">
              <table className="pis-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th onClick={() => handleSort('location_key')} className="sortable">
                      Junction <SortIcon k="location_key" activeK={sortKey} dir={sortDir} />
                    </th>
                    <th onClick={() => handleSort('pis_score')} className="sortable">
                      PIS Score <SortIcon k="pis_score" activeK={sortKey} dir={sortDir} />
                    </th>
                    <th onClick={() => handleSort('loss_inr_per_day')} className="sortable">
                      ₹ Loss/Day <SortIcon k="loss_inr_per_day" activeK={sortKey} dir={sortDir} />
                    </th>
                    <th onClick={() => handleSort('vehicle_hours_lost_per_day')} className="sortable">
                      Veh·Hrs Lost/Day <SortIcon k="vehicle_hours_lost_per_day" activeK={sortKey} dir={sortDir} />
                    </th>
                    <th onClick={() => handleSort('mean_blockage_severity')} className="sortable">
                      Blockage Sev. <SortIcon k="mean_blockage_severity" activeK={sortKey} dir={sortDir} />
                    </th>
                    <th onClick={() => handleSort('enforcement_failure_rate')} className="sortable">
                      Enforcement Gap <SortIcon k="enforcement_failure_rate" activeK={sortKey} dir={sortDir} />
                    </th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedPIS.map((row, i) => (
                    <tr
                      key={row.location_key}
                      className={`${row.action_type === 'Intervene' ? 'row-intervene' : ''} pis-row-clickable`}
                      onClick={() => setSelectedJunction(row)}
                    >
                      <td className="pis-rank">#{row.rank ?? i + 1}</td>
                      <td>
                        <div className="pis-junction">{row.location_key.replace(/^[A-Z0-9]+ - /, '')}</div>
                        <div className="pis-station">{row.police_station || row.area || '—'}</div>
                      </td>
                      <td className="pis-score-cell">
                        <span className="pis-score-val">{fmt(row.pis_score, 1)}</span>
                        <div className="pis-score-bar">
                          <div
                            className="pis-score-fill"
                            style={{
                              width: `${Math.min(100, (row.pis_score / (displayedPIS[0]?.pis_score || 1)) * 100).toFixed(1)}%`,
                            }}
                          />
                        </div>
                      </td>
                      <td className="pis-money">{fmtInr(row.loss_inr_per_day)}</td>
                      <td>{fmt(row.vehicle_hours_lost_per_day, 1)}</td>
                      <td>
                        <div className="pis-severity-bar">
                          <div
                            className="pis-severity-fill"
                            style={{ width: `${Math.min(100, (row.mean_blockage_severity / 7) * 100).toFixed(0)}%` }}
                          />
                          <span>{fmt(row.mean_blockage_severity, 2)}</span>
                        </div>
                      </td>
                      <td>{fmtPct(row.enforcement_failure_rate)}</td>
                      <td>
                        <span className={`pis-action-badge ${row.action_type === 'Intervene' ? 'intervene' : 'monitor'}`}>
                          {row.action_type}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Station Performance Table ────────────────────────────── */}
      {activeTab === 'station' && (
        <div className="pis-content">
          {statLoading ? (
            <div className="pis-loading"><Loader2 size={24} className="spin-icon" /><p>Loading station data…</p></div>
          ) : displayedStats.length === 0 ? (
            <div className="pis-empty">
              Station performance data unavailable (dataset.csv may not include validation_status).
            </div>
          ) : (
            <div className="pis-table-wrap">
              <table className="pis-table">
                <thead>
                  <tr>
                    <th onClick={() => { setStatSort('police_station'); setStatSortDir(d => d === 'asc' ? 'desc' : 'asc'); }} className="sortable">
                      Police Station
                    </th>
                    <th onClick={() => { setStatSort('total_violations'); setStatSortDir(d => d === 'asc' ? 'desc' : 'asc'); }} className="sortable">
                      Total Violations
                    </th>
                    <th onClick={() => { setStatSort('rejection_rate'); setStatSortDir(d => d === 'asc' ? 'desc' : 'asc'); }} className="sortable">
                      Rejection Rate
                    </th>
                    <th onClick={() => { setStatSort('violations_per_device'); setStatSortDir(d => d === 'asc' ? 'desc' : 'asc'); }} className="sortable">
                      Violations/Device
                    </th>
                    <th onClick={() => { setStatSort('median_validation_lag_hours'); setStatSortDir(d => d === 'asc' ? 'desc' : 'asc'); }} className="sortable">
                      Median Lag (hrs)
                    </th>
                    <th>Flag</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedStats.map(row => (
                    <tr key={row.police_station} className={row.flag_high_rejection ? 'row-flagged' : ''}>
                      <td className="pis-junction">{row.police_station}</td>
                      <td>{fmt(row.total_violations)}</td>
                      <td>
                        <span className={row.rejection_rate > 0.35 ? 'pis-high-rejection' : ''}>
                          {fmtPct(row.rejection_rate)}
                        </span>
                      </td>
                      <td>{fmt(row.violations_per_device, 1)}</td>
                      <td>{row.median_validation_lag_hours != null ? fmt(row.median_validation_lag_hours, 1) : '—'}</td>
                      <td>
                        {row.flag_high_rejection && (
                          <span className="pis-flag"><Flag size={12} /> High</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Junction Drawer ───────────────────────────────── */}
      {selectedJunction && (
        <JunctionDrawer
          junction={selectedJunction}
          onClose={() => setSelectedJunction(null)}
        />
      )}
    </div>
  );
}

function JunctionDrawer({ junction, onClose }) {
  const mapRef = useRef(null);
  const leafletMap = useRef(null);

  useEffect(() => {
    if (!mapRef.current) return;
    const lat = parseFloat(junction.latitude);
    const lng = parseFloat(junction.longitude);
    if (isNaN(lat) || isNaN(lng)) return;

    const m = L.map(mapRef.current, { center: [lat, lng], zoom: 15, zoomControl: false });
    L.control.zoom({ position: 'bottomright' }).addTo(m);
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
      { attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 19 }
    ).addTo(m);
    L.circleMarker([lat, lng], { radius: 10, fillColor: '#ef4444', fillOpacity: 1, color: '#fff', weight: 2 }).addTo(m);
    leafletMap.current = m;

    return () => { m.remove(); leafletMap.current = null; };
  }, [junction.location_key]);

  const lat = parseFloat(junction.latitude);
  const lng = parseFloat(junction.longitude);
  const name = junction.location_key.replace(/^[A-Z0-9]+ - /, '');

  return (
    <div className="pis-drawer-overlay" onClick={onClose}>
      <div className="pis-drawer" onClick={e => e.stopPropagation()}>
        <div className="pis-drawer-header">
          <div>
            <h3 className="pis-drawer-title">{name}</h3>
            <p className="pis-drawer-sub">{junction.police_station || junction.area || '—'}</p>
          </div>
          <button className="pis-drawer-close" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="pis-drawer-stats">
          <div className="pis-drawer-stat">
            <span>PIS Score</span>
            <strong>{junction.pis_score != null ? Number(junction.pis_score).toFixed(1) : '—'}</strong>
          </div>
          <div className="pis-drawer-stat">
            <span>₹ Loss/Day</span>
            <strong style={{ color: '#16a34a' }}>
              {junction.loss_inr_per_day != null
                ? `₹${(junction.loss_inr_per_day / 1e5).toFixed(2)}L`
                : '—'}
            </strong>
          </div>
          <div className="pis-drawer-stat">
            <span>Action</span>
            <strong>
              <span className={`pis-action-badge ${junction.action_type === 'Intervene' ? 'intervene' : 'monitor'}`}>
                {junction.action_type}
              </span>
            </strong>
          </div>
        </div>

        <p className="pis-drawer-coords">
          {!isNaN(lat) && !isNaN(lng) ? `${lat.toFixed(5)}, ${lng.toFixed(5)}` : 'Coordinates unavailable'}
        </p>

        <div ref={mapRef} className="pis-drawer-map" />

        {!isNaN(lat) && !isNaN(lng) && (
          <a
            className="pis-drawer-maps-link"
            href={`https://maps.google.com/?q=${lat},${lng}`}
            target="_blank"
            rel="noreferrer"
          >
            Open in Google Maps →
          </a>
        )}
      </div>
    </div>
  );
}
