// PCU (Passenger Car Unit) factors — IRC SP-41-1994 standard
const PCU = {
  two_wheeler:   0.5,
  auto_rickshaw: 1.2,
  car:           1.0,
  lcv:           1.5,
  bus:           2.5,
  heavy_truck:   3.0,
  tractor:       4.0,
};

const VEH_LABEL = {
  two_wheeler:   'two-wheelers',
  auto_rickshaw: 'auto-rickshaws',
  car:           'cars',
  lcv:           'light commercial vehicles',
  bus:           'buses',
  heavy_truck:   'heavy trucks',
  tractor:       'tractors',
};

const VEH_EMOJI = {
  two_wheeler:   '🛵',
  auto_rickshaw: '🛺',
  car:           '🚗',
  lcv:           '🚐',
  bus:           '🚌',
  heavy_truck:   '🚛',
  tractor:       '🚜',
};

/**
 * Generates a plain-English explanation of why a location has a high severity score.
 *
 * @param {object} pred — a severity prediction record from /api/v1/traffic-severity/predict
 * @returns {{ headline: string, detail: string, emoji: string, blockagePct: number }}
 */
export function getSeverityNarrative(pred) {
  const vehicleCat  = pred.dominant_vehicle_cat;
  const laneCount   = pred.lane_count != null ? parseFloat(pred.lane_count) : null;
  const violation   = pred.dominant_violation;
  const score       = pred.lightgbm_prediction || 0;

  const pcu      = PCU[vehicleCat] || 1.0;
  const emoji    = VEH_EMOJI[vehicleCat] || '🚗';
  const vehLabel = VEH_LABEL[vehicleCat] || 'vehicles';

  const blockagePct = laneCount && laneCount > 0
    ? Math.min(100, Math.round((pcu / laneCount) * 100))
    : Math.min(100, Math.round(pcu * 40));

  let headline;
  if (blockagePct >= 90) {
    headline = `${emoji} Full carriageway blocked by ${vehLabel}`;
  } else if (blockagePct >= 60) {
    headline = `${emoji} ${blockagePct}% of road blocked by ${vehLabel}`;
  } else if (blockagePct >= 35) {
    headline = `${emoji} Partial blockage — ${vehLabel} spilling onto road`;
  } else {
    headline = `${emoji} Recurring ${vehLabel} spillover`;
  }

  let detail = '';

  if (laneCount != null) {
    const laneWord = laneCount <= 1 ? 'single-lane' : `${Math.round(laneCount)}-lane`;
    if (blockagePct >= 90) {
      detail += `A ${vehLabel.replace(/s$/, '')} (${pcu} PCU) on this ${laneWord} road leaves no room for other traffic. `;
    } else {
      detail += `${capitalize(vehLabel)} (${pcu} PCU each) reduce usable width on this ${laneWord} road by ~${blockagePct}%. `;
    }
  } else {
    detail += `${capitalize(vehLabel)} are the primary offenders at this location. `;
  }

  if (violation && violation.toLowerCase() !== 'unknown') {
    detail += `Most common violation: "${violation}". `;
  }

  if (score >= 8) {
    detail += 'Immediate enforcement needed — this junction has critical impact on network flow.';
  } else if (score >= 4) {
    detail += 'Elevated impact — peak-hour patrol recommended.';
  } else {
    detail += 'Monitor during peak hours.';
  }

  return { headline, detail, emoji, blockagePct };
}

/**
 * Short label for compact list items (EnforcementSidebar ranks 4–10).
 */
export function getSeverityShortLabel(pred) {
  const vehicleCat = pred.dominant_vehicle_cat;
  const laneCount  = pred.lane_count;
  const pcu        = PCU[vehicleCat] || 1.0;
  const veh        = VEH_LABEL[vehicleCat] || 'vehicles';
  const pct        = laneCount
    ? Math.min(100, Math.round((pcu / laneCount) * 100))
    : null;
  return pct != null ? `${pct}% blockage · ${veh}` : veh;
}

function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
}
