// flood.js — rules-based flood-risk lookup over curated Mumbai hotspots.
// Pure functions, reused by the unit tests.
//
// This is a hazard heuristic, not a hydrodynamic model: it combines the
// next-2h corrected rain peak with how chronically a nearby spot floods.
// Upgrade path: a flood-depth surrogate trained on historical waterlogging.

// Nearest curated hotspot to (lat, lon) by squared degree distance.
// Good enough at city scale; avoids a sqrt we don't need for a min.
export function nearestZone(lat, lon, zones) {
  let best = null;
  let bestD = Infinity;
  for (const z of zones) {
    const d = (z.lat - lat) ** 2 + (z.lon - lon) ** 2;
    if (d < bestD) {
      bestD = d;
      best = z;
    }
  }
  return best;
}

// Combine forecast peak (mm/h) with zone severity (1..3) into a level.
// score = peakMm * severity, so a chronic spot escalates faster than a mild one.
export function floodRisk(peakMm, zone) {
  const severity = zone ? zone.severity : 1;
  const score = peakMm * severity;
  if (score >= 12)
    return { level: "high", reason: `heavy rain over ${zone.name} (chronic flood spot)` };
  if (score >= 4)
    return { level: "watch", reason: `rain building over ${zone.name}` };
  return { level: "low", reason: "no significant pooling expected" };
}
