// /api/nowcast — the Mumbai Rain API. Query a Mumbai spot (lat/lon or locality
// name/slug) and get the calibrated nowcast verdict as JSON — the same math the
// UI runs, served server-side so anything can call it.
//
//   GET /api/nowcast?lat=19.06&lon=72.83&hours=2
//   GET /api/nowcast?locality=bandra&hours=3
//   GET /api/nowcast?locality=Andheri%20East
//
// Pure on top of the SAME modules the island uses (nowcast.js, flood.js,
// open-meteo.js) — serving parity is structural, not re-implemented.
import { verdict } from "../../lib/nowcast.js";
import { nearestZone, floodRisk } from "../../lib/flood.js";
import { fetchWeather, shapeForecast } from "../../lib/open-meteo.js";
import localities from "../../data/localities.json";
import zones from "../../data/flood-zones.json";

export const prerender = false;

const MAX_HOURS = 24;
const MIN_HOURS = 1;

// Resolve a spot from the curated 146 areas — by exact name OR slug, either case.
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

function resolveLocality(q) {
  const needle = String(q || "").trim().toLowerCase();
  if (!needle) return null;
  return (
    localities.find((l) => l.name.toLowerCase() === needle) ||
    localities.find((l) => slug(l.name) === needle) ||
    null
  );
}

const badRequest = (detail) =>
  new Response(JSON.stringify({ error: "bad_request", detail }), {
    status: 400,
    headers: { "Content-Type": "application/json" },
  });

// Load the deployed model.json from the same origin the browser uses. Always in
// sync with what the site ships (every promotion rebuilds), and cached by the CDN.
async function loadModel(request) {
  const origin = new URL(request.url).origin;
  const r = await fetch(`${origin}/model.json`, { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`model.json ${r.status}`);
  return r.json();
}

export async function GET({ request }) {
  const url = new URL(request.url);
  const latP = url.searchParams.get("lat");
  const lonP = url.searchParams.get("lon");
  const localityQ = url.searchParams.get("locality");
  const hoursRaw = url.searchParams.get("hours");
  const hours = hoursRaw ? Number(hoursRaw) : 2;

  if (!Number.isFinite(hours) || hours < MIN_HOURS || hours > MAX_HOURS) {
    return badRequest(`hours must be an integer between ${MIN_HOURS} and ${MAX_HOURS}`);
  }

  // Resolve the spot: explicit lat/lon wins; else a curated locality name/slug.
  const hasCoords =
    latP !== null && lonP !== null && Number.isFinite(Number(latP)) && Number.isFinite(Number(lonP));
  let spot;
  if (hasCoords) {
    spot = { name: localityQ || `${latP},${lonP}`, lat: Number(latP), lon: Number(lonP) };
  } else {
    spot = resolveLocality(localityQ);
    if (!spot) {
      return badRequest(
        "pass lat & lon (e.g. ?lat=19.06&lon=72.83), or a locality name/slug (e.g. ?locality=bandra)",
      );
    }
  }

  let model;
  try {
    model = await loadModel(request);
  } catch (err) {
    console.error("model load failed", err);
    return new Response(JSON.stringify({ error: "model_unavailable", detail: String(err) }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }

  let fc;
  let current;
  try {
    const data = await fetchWeather(spot.lat, spot.lon);
    current = data.current;
    fc = shapeForecast(data);
  } catch (err) {
    console.error("open-meteo fetch failed", err);
    return new Response(JSON.stringify({ error: "forecast_unavailable", detail: String(err) }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  const v = verdict(model, fc, fc.nowHour, fc.recentRain, hours);
  const zone = nearestZone(spot.lat, spot.lon, zones);
  const fr = floodRisk(v.peakMm, zone);

  const body = {
    spot,
    fetched_at: new Date().toISOString(),
    window_hours: v.horizon,
    model: {
      type: model.type ?? "linear",
      trained_at: model.trained_at ?? null,
      n_train: model.n_train ?? null,
      brier: model.brier ?? null,
    },
    verdict: v,
    flood: fr,
    measured: {
      precipitation_mm:
        typeof current?.precipitation === "number" ? current.precipitation : null,
    },
    source: "Open-Meteo (keyless) + calibrated model.json",
    docs: "/api/nowcast?lat=&lon=&hours=",
  };

  return new Response(JSON.stringify(body, null, 2), {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, s-maxage=300, max-age=120",
    },
  });
}
