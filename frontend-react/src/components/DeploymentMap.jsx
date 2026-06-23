import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { sevRiskColor } from '../utils/colorUtils';
import './HeatMap.css';

const BENGALURU_CENTER = [12.9716, 77.5946];
const TILE_URL  = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

export const OFFICER_COLORS = [
  '#3b82f6','#8b5cf6','#f59e0b','#10b981','#ef4444',
  '#06b6d4','#f97316','#84cc16','#ec4899','#14b8a6',
  '#6366f1','#a78bfa','#fb923c','#34d399','#f87171',
  '#22d3ee','#fbbf24','#a3e635','#f472b6','#2dd4bf',
  '#1d4ed8','#7c3aed','#d97706','#059669','#dc2626',
  '#0891b2','#ea580c','#65a30d','#db2777','#0d9488',
  '#4f46e5','#9333ea','#b45309','#047857','#b91c1c',
  '#0e7490','#c2410c','#4d7c0f','#be185d','#0f766e',
  '#3730a3','#6b21a8','#92400e','#064e3b','#7f1d1d',
  '#164e63','#7c2d12','#365314','#500724','#042f2e',
];

const DeploymentMap = ({ deployment, patrolRadius, displayTopN = 500 }) => {
  const mapRef        = useRef(null);
  const leafletMap    = useRef(null);
  const canvasRenderer = useRef(null);
  const hotspotLayer  = useRef(null);
  const coverageLayer = useRef(null);
  const officerLayer  = useRef(null);

  // Init map once
  useEffect(() => {
    if (leafletMap.current) return;
    canvasRenderer.current = L.canvas({ padding: 0.5 });
    const m = L.map(mapRef.current, {
      center: BENGALURU_CENTER,
      zoom: 11,
      preferCanvas: true,
      zoomControl: false,
    });
    L.control.zoom({ position: 'bottomright' }).addTo(m);
    L.tileLayer(TILE_URL, { attribution: TILE_ATTR, maxZoom: 19 }).addTo(m);
    leafletMap.current = m;
    return () => { m.remove(); leafletMap.current = null; };
  }, []);

  // Invalidate size fix
  useEffect(() => {
    const t = setTimeout(() => {
      if (leafletMap.current) leafletMap.current.invalidateSize();
    }, 80);
    return () => clearTimeout(t);
  });

  // Re-render when deployment changes
  useEffect(() => {
    const m = leafletMap.current;
    if (!m) return;

    [hotspotLayer, coverageLayer, officerLayer].forEach(ref => {
      if (ref.current) { m.removeLayer(ref.current); ref.current = null; }
    });

    if (!deployment) return;

    const { assignments, coveredSet, active } = deployment;
    const maxScore = active.length ? active[0]._score : 1;

    // Map each covered location to its assignment's color
    const locToColor = new Map();
    assignments.forEach((a, i) => {
      const color = OFFICER_COLORS[i % OFFICER_COLORS.length];
      a.covered.forEach(p => locToColor.set(p.location_key, color));
    });

    // 1. Coverage circles — radius scales with officer count (more officers = wider effective reach)
    const covLayer = L.layerGroup();
    assignments.forEach((a, i) => {
      const color = OFFICER_COLORS[i % OFFICER_COLORS.length];
      L.circle([a.location._lat, a.location._lng], {
        radius: patrolRadius,
        color,
        fillColor: color,
        fillOpacity: 0.07,
        weight: 2,
        opacity: 0.45,
        dashArray: '7 5',
      }).addTo(covLayer);
    });
    covLayer.addTo(m);
    coverageLayer.current = covLayer;

    // 2. Hotspot circles
    const hLayer = L.layerGroup();
    active.slice(0, displayTopN).forEach((loc, idx) => {
      const isCovered = coveredSet.has(loc.location_key);
      const ratio     = maxScore > 0 ? loc._score / maxScore : 0;
      const heatColor = sevRiskColor(ratio);
      const officerColor = locToColor.get(loc.location_key);

      const radius      = idx < 5 ? 14 : idx < 20 ? 10 : idx < 100 ? 7 : 5;
      const fillColor   = isCovered ? heatColor : '#94a3b8';
      const fillOpacity = isCovered ? (idx < 5 ? 0.95 : 0.75) : 0.3;
      const borderColor = isCovered ? (officerColor || '#22c55e') : '#cbd5e1';
      const borderWeight = isCovered ? 2 : 0.8;

      const circle = L.circleMarker([loc._lat, loc._lng], {
        renderer:    canvasRenderer.current,
        radius,
        fillColor,
        fillOpacity,
        color:       borderColor,
        weight:      borderWeight,
        bubblingMouseEvents: false,
      });

      const covStatus = isCovered
        ? `<span style="color:#22c55e;font-weight:700">✓ Covered</span>`
        : `<span style="color:#94a3b8">○ Not covered</span>`;

      circle.bindPopup(`
        <div style="font-family:Inter,sans-serif;min-width:190px">
          <div style="font-weight:800;font-size:13px;margin-bottom:4px">#${idx + 1} ${loc.location_key}</div>
          <div style="font-size:11px;color:#6b7280;margin-bottom:6px">${loc.area || '—'} · ${loc.police_station || '—'}</div>
          <div style="font-size:12px;margin-bottom:4px">${covStatus}</div>
          <div style="font-size:12px">Severity score: <strong>${loc._score.toFixed(2)}</strong></div>
        </div>`, { maxWidth: 260 });

      hLayer.addLayer(circle);
    });
    hLayer.addTo(m);
    hotspotLayer.current = hLayer;

    // 3. Officer pins — one pin per assignment, badge shows how many officers are here
    const oLayer = L.layerGroup();
    assignments.forEach((a, i) => {
      const color = OFFICER_COLORS[i % OFFICER_COLORS.length];
      const multi = a.officerCount > 1;

      // Pin label: first officer number; if multiple, show "N–M"
      const endNum = a.startNum + a.officerCount - 1;
      const label  = multi ? `${a.startNum}–${endNum}` : `${a.startNum}`;

      // Multi-officer pins are larger and show a ×N reinforcement badge
      const pinSize = multi ? 40 : 34;
      const fontSize = multi ? 11 : 14;
      const badge = multi
        ? `<div style="
            position:absolute;top:-6px;right:-6px;
            background:#fff;color:${color};
            font-size:9px;font-weight:900;
            border-radius:8px;padding:1px 5px;
            border:1.5px solid ${color};
            box-shadow:0 1px 4px rgba(0,0,0,0.25);
            white-space:nowrap;
          ">×${a.officerCount}</div>`
        : '';

      const icon = L.divIcon({
        html: `<div style="position:relative;width:${pinSize}px;height:${pinSize}px;">
          <div style="
            width:${pinSize}px;height:${pinSize}px;border-radius:50%;
            background:${color};color:#fff;
            font-size:${fontSize}px;font-weight:900;font-family:Inter,sans-serif;
            display:flex;align-items:center;justify-content:center;
            border:3px solid #fff;
            box-shadow:0 3px 10px rgba(0,0,0,0.35);
            cursor:pointer;
          ">${label}</div>
          ${badge}
        </div>`,
        className: '',
        iconSize:   [pinSize, pinSize],
        iconAnchor: [pinSize / 2, pinSize / 2],
      });

      const violHr = a.covered.reduce((s, p) => s + (p.naive_prediction || p.baseline_prediction || 0), 0);
      const officerRange = multi
        ? `Officers ${a.startNum}–${endNum} (${a.officerCount} units)`
        : `Officer ${a.startNum}`;
      const reasonNote = multi
        ? `<div style="font-size:11px;color:${color};margin-top:4px;font-style:italic">
            High congestion — ${a.officerCount} officers needed here
           </div>`
        : '';

      L.marker([a.location._lat, a.location._lng], { icon, zIndexOffset: 2000 })
        .bindPopup(`
          <div style="font-family:Inter,sans-serif;min-width:210px">
            <div style="font-weight:800;font-size:14px;color:${color};margin-bottom:2px">${officerRange}</div>
            ${reasonNote}
            <div style="font-size:12px;font-weight:600;margin-top:6px;margin-bottom:2px">${a.location.location_key}</div>
            <div style="font-size:11px;color:#6b7280;margin-bottom:8px">${a.location.area || '—'}</div>
            <div style="display:flex;gap:16px;font-size:12px">
              <div><div style="color:#6b7280;font-size:10px;text-transform:uppercase">Hotspots</div><strong>${a.covered.length}</strong></div>
              <div><div style="color:#6b7280;font-size:10px;text-transform:uppercase">Score</div><strong>${a.coveredScore.toFixed(1)}</strong></div>
              <div><div style="color:#6b7280;font-size:10px;text-transform:uppercase">Viol/hr</div><strong>${violHr.toFixed(0)}</strong></div>
            </div>
          </div>`, { maxWidth: 270 })
        .addTo(oLayer);
    });
    oLayer.addTo(m);
    officerLayer.current = oLayer;

  }, [deployment, patrolRadius, displayTopN]);

  return (
    <div className="heatmap-wrapper">
      <div ref={mapRef} className="heatmap-leaflet" />
    </div>
  );
};

export default DeploymentMap;
