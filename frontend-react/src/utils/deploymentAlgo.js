function haversineM(lat1, lng1, lat2, lng2) {
  const R = 6371000;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Officers are allocated proportional to how severe a hotspot is relative to the
// "per-officer share" of total severity. A road with 3× the average congestion gets
// 3 officers before we move on to the next hotspot.
export function computeDeployment(predictions, key, officerCount, patrolRadius) {
  const active = predictions
    .map(p => ({
      ...p,
      _lat: parseFloat(p.latitude),
      _lng: parseFloat(p.longitude),
      _score: p[key] || 0,
    }))
    .filter(p => !isNaN(p._lat) && !isNaN(p._lng))
    .sort((a, b) => b._score - a._score);

  const totalScore = active.reduce((s, p) => s + p._score, 0);

  // How much severity one officer is expected to handle
  const scorePerOfficer = totalScore / Math.max(officerCount, 1);

  const coveredSet = new Set();
  const assignments = [];
  let officersUsed = 0;

  for (const target of active) {
    if (officersUsed >= officerCount) break;
    if (coveredSet.has(target.location_key)) continue;

    const remaining = officerCount - officersUsed;

    // Officers this hotspot deserves: score / per-officer-share, minimum 1
    // Cap at half the remaining pool so one hotspot never consumes everything
    const deserved  = Math.max(1, Math.round(target._score / scorePerOfficer));
    const officersHere = Math.min(deserved, Math.max(1, Math.ceil(remaining / 2)), remaining);

    // Mark all locations within patrol radius as covered (same regardless of officer count)
    const newlyCovered = [];
    for (const p of active) {
      if (coveredSet.has(p.location_key)) continue;
      if (haversineM(target._lat, target._lng, p._lat, p._lng) <= patrolRadius) {
        coveredSet.add(p.location_key);
        newlyCovered.push(p);
      }
    }

    assignments.push({
      startNum:     officersUsed + 1,
      officerCount: officersHere,
      location:     target,
      covered:      newlyCovered,
      coveredScore: newlyCovered.reduce((s, p) => s + p._score, 0),
    });

    officersUsed += officersHere;
  }

  const coveredScore = active
    .filter(p => coveredSet.has(p.location_key))
    .reduce((s, p) => s + p._score, 0);

  const nextBest = active.find(p => !coveredSet.has(p.location_key));

  let nextBestGain = 0;
  if (nextBest) {
    for (const p of active) {
      if (!coveredSet.has(p.location_key) &&
          haversineM(nextBest._lat, nextBest._lng, p._lat, p._lng) <= patrolRadius) {
        nextBestGain += p._score;
      }
    }
  }

  return {
    assignments,
    coveredSet,
    coveredScore,
    totalScore,
    coveragePct:     totalScore > 0 ? (coveredScore / totalScore) * 100 : 0,
    nextBest,
    nextBestGainPct: totalScore > 0 ? (nextBestGain / totalScore) * 100 : 0,
    officersUsed,
    active,
  };
}
