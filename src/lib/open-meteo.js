// open-meteo.js — the one place that talks to Open-Meteo (server + client parity).
// Mirrors the island in Almanac.astro exactly: one keyless fetch, shaped into the
// forecast object nowcast.js expects. Shared by the /api/nowcast route so the
// API verdict is computed from the SAME source shape as the UI.
//
// Two models in ONE request (best_match + ECMWF-IFS) + relative humidity, so the
// served feature vector matches what train.py fits (fc_bestmatch_mm,
// fc_ecmwf_mm, fc_rh_bestmatch, ...). Open-Meteo suffixes keys per model when
// models=best_match,ecmwf_ifs025 is requested.

const API = "https://api.open-meteo.com/v1/forecast";

export async function fetchWeather(lat, lon) {
  const url =
    `${API}?latitude=${lat}&longitude=${lon}` +
    `&hourly=precipitation,relative_humidity_2m` +
    `&models=best_match,ecmwf_ifs025` +
    `&current=precipitation,rain,weather_code` +
    `&forecast_days=2&past_days=1&timezone=Asia%2FKolkata`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Open-Meteo ${r.status}`);
  return r.json();
}

// Build the forecast object nowcast.js expects, sliced from the current hour.
// Open-Meteo times are already IST (timezone=Asia/Kolkata). With two models the
// hourly keys carry per-model suffixes; best_match drives the time axis.
export function shapeForecast(data) {
  const h = data.hourly;
  const times = h.time;
  const best = h.precipitation_best_match ?? h.precipitation;
  const ecmwf = h.precipitation_ecmwf_ifs025 ?? best;
  const rh = h.relative_humidity_2m_best_match ?? h.relative_humidity_2m ?? null;
  const nowStamp = data.current.time.slice(0, 13);
  let i = times.findIndex((t) => t.slice(0, 13) >= nowStamp);
  if (i < 0) i = times.length - 1;

  const recentRain = best
    .slice(Math.max(0, i - 3), i)
    .reduce((s, v) => s + (v || 0), 0);

  return {
    valid_at: times.slice(i),
    fc_bestmatch_mm: best.slice(i).map((v) => v || 0),
    fc_ecmwf_mm: ecmwf.slice(i).map((v) => (v == null ? 0 : v)),
    fc_rh_bestmatch: rh
      ? rh.slice(i).map((v) => (v == null ? 50 : v))
      : best.slice(i).map(() => 50), // no RH in payload -> neutral 50% (train default)
    nowHour: Number(nowStamp.slice(11, 13)),
    recentRain,
  };
}
