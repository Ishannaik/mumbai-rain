// open-meteo.js — the one place that talks to Open-Meteo (server + client parity).
// Mirrors the island in Almanac.astro exactly: one keyless fetch, shaped into the
// forecast object nowcast.js expects. Shared by the /api/nowcast route so the
// API verdict is computed from the SAME source shape as the UI.

const API = "https://api.open-meteo.com/v1/forecast";

export async function fetchWeather(lat, lon) {
  const url =
    `${API}?latitude=${lat}&longitude=${lon}` +
    `&hourly=precipitation&current=precipitation,rain,weather_code` +
    `&forecast_days=2&past_days=1&timezone=Asia%2FKolkata`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Open-Meteo ${r.status}`);
  return r.json();
}

// Build the forecast object nowcast.js expects, sliced from the current hour.
// Open-Meteo times are already IST (timezone=Asia/Kolkata).
export function shapeForecast(data) {
  const times = data.hourly.time;
  const precip = data.hourly.precipitation;
  const nowStamp = data.current.time.slice(0, 13);
  let i = times.findIndex((t) => t.slice(0, 13) >= nowStamp);
  if (i < 0) i = times.length - 1;

  const recentRain = precip
    .slice(Math.max(0, i - 3), i)
    .reduce((s, v) => s + (v || 0), 0);

  const fc_bestmatch_mm = precip.slice(i).map((v) => v || 0);
  return {
    valid_at: times.slice(i),
    fc_bestmatch_mm,
    fc_ecmwf_mm: fc_bestmatch_mm.slice(), // mirror; single-model fetch
    nowHour: Number(nowStamp.slice(11, 13)),
    recentRain,
  };
}
