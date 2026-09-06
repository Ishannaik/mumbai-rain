// flood.js — rules-based flood-risk lookup over curated Mumbai hotspots.
// Pure functions, reused by the unit tests.
//
// This is a hazard heuristic, not a hydrodynamic model: it combines the
// next-2h corrected rain peak with how chronically a nearby spot floods.
// Upgrade path: a flood-depth surrogate trained on historical waterlogging.

// Nearest curated hotspot to (lat, lon) by squared degree distance.
// ~0.5° ≈ 55 km: covers MMR, excludes Pune/Chennai. Avoids a sqrt we don't
// need for a min. Too-far queries return null so the UI hides flood watch.
const MAX_DEG2 = 0.5 * 0.5;

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
  if (best == null || bestD > MAX_DEG2) return null;
  return best;
}

// Combine forecast peak (mm/h) with zone severity (1..3) into a level.
// score = peakMm * severity, so a chronic spot escalates faster than a mild one.
export function floodRisk(peakMm, zone) {
  if (!zone) return { level: "low", reason: "no flood map for this area" };
  const score = peakMm * zone.severity;
  if (score >= 12)
    return { level: "high", reason: `heavy rain over ${zone.name} (chronic flood spot)` };
  if (score >= 4)
    return { level: "watch", reason: `rain building over ${zone.name}` };
  return { level: "low", reason: "no significant pooling expected" };
}
