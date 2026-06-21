function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function lerpColor(hex1, hex2, t) {
  const [r1, g1, b1] = hexToRgb(hex1);
  const [r2, g2, b2] = hexToRgb(hex2);
  return `rgb(${Math.round(r1 + (r2 - r1) * t)},${Math.round(g1 + (g2 - g1) * t)},${Math.round(b1 + (b2 - b1) * t)})`;
}

// Count heatmap: green → amber → red
export function riskColor(ratio) {
  if (ratio <= 0) return '#22c55e';
  if (ratio >= 1) return '#ef4444';
  if (ratio < 0.5) return lerpColor('#22c55e', '#f59e0b', ratio * 2);
  return lerpColor('#f59e0b', '#ef4444', (ratio - 0.5) * 2);
}

// Severity heatmap: emerald → amber → deep orange → crimson
export function sevRiskColor(ratio) {
  if (ratio <= 0)   return '#10b981';
  if (ratio >= 1)   return '#dc2626';
  if (ratio < 0.4)  return lerpColor('#10b981', '#f59e0b', ratio / 0.4);
  if (ratio < 0.7)  return lerpColor('#f59e0b', '#ea580c', (ratio - 0.4) / 0.3);
  return lerpColor('#ea580c', '#dc2626', (ratio - 0.7) / 0.3);
}

export function toDatetimeLocalValue(d) {
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

export function scoreKey(model) {
  return `${model}_prediction`;
}

export const VEH_LABELS = {
  two_wheeler: 'two-wheeler', auto_rickshaw: 'auto-rickshaw',
  car: 'car', lcv: 'light commercial vehicle',
  bus: 'bus', heavy_truck: 'heavy truck', tractor: 'tractor',
};

export const VEH_SHORT = {
  two_wheeler: '2W', auto_rickshaw: 'Auto', car: 'Car',
  lcv: 'LCV', bus: 'Bus', heavy_truck: 'HGV', tractor: 'Tractor',
};
