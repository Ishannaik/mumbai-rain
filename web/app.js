// app.js — UI wiring: geolocate, fetch live Open-Meteo, run the model,
// render the verdict + flood + ground reality, and drive the rain canvas.
import { verdict } from "./nowcast.js";
import { nearestZone, floodRisk } from "./flood.js";

const API = "https://api.open-meteo.com/v1/forecast";

// --- DOM handles ---
const app = document.getElementById("app");
const sel = document.getElementById("locality");
const elVerdict = document.getElementById("verdict");
const elSub = document.getElementById("verdict-sub");
const elLeave = document.getElementById("leave");
const elMeasured = document.getElementById("measured");
const elFloodRow = document.getElementById("flood-row");
const elFlood = document.getElementById("flood");
const elHonesty = document.getElementById("honesty");

let MODEL, ZONES, LOCALITIES;
let activeLoc = null;        // currently shown {name, lat, lon}
let reqToken = 0;            // guards against out-of-order async renders

const json = (path) => fetch(path).then((r) => r.json());

// --- Open-Meteo ---
// One keyless fetch: hourly precip (with 1 past day for recent-rain), plus the
// `current` block for measured-now. We only fetch best_match; the model's
// fc_ecmwf_mm feature mirrors it (weight 0 in the seeded identity model).
async function fetchWeather(lat, lon) {
  const url =
    `${API}?latitude=${lat}&longitude=${lon}` +
    `&hourly=precipitation&current=precipitation,rain,weather_code` +
    `&forecast_days=1&past_days=1&timezone=Asia%2FKolkata`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Open-Meteo ${r.status}`);
  return r.json();
}

// Build the forecast object nowcast.js expects, sliced from the current hour.
// Times are local (Asia/Kolkata) naive ISO strings, so we match on local hour.
function shapeForecast(data) {
  const times = data.hourly.time;
  const precip = data.hourly.precipitation;

  // Index of the current local hour, e.g. "2026-06-24T21".
  const nowStamp = data.current.time.slice(0, 13);
  let i = times.findIndex((t) => t.slice(0, 13) >= nowStamp);
  if (i < 0) i = times.length - 1;

  // Recent rain = sum of the prior 3 hourly precip values (persistence signal).
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

// --- Rendering ---
function setState(cls) {
  app.className = cls; // exactly one state-* class at a time
}

function renderVerdict(v) {
  if (v.willRain && v.startsInHrs === 0) {
    setState("state-now");
    elVerdict.textContent = "Raining now";
    elSub.textContent = `~${v.peakMm} mm/h overhead`;
  } else if (v.willRain) {
    setState("state-incoming");
    elVerdict.textContent = `Rain in ~${v.startsInHrs}h`;
    elSub.textContent = `peaking ~${v.peakMm} mm/h`;
  } else {
    setState("state-dry");
    elVerdict.textContent = "Dry for the next 2h";
    elSub.textContent = "Go — no rain at your spot ☀️";
  }
}

function renderLeave(v) {
  // Show only when rain is incoming (not already falling). Rough: hrs → minutes.
  if (v.willRain && v.startsInHrs > 0) {
    const mins = v.startsInHrs * 60;
    elLeave.textContent = `Leave in the next ~${mins} min to stay dry.`;
    elLeave.hidden = false;
  } else {
    elLeave.hidden = true;
  }
}

function renderMeasured(current) {
  // Ground reality (honesty): distinguish what's measured now vs forecast.
  const mm = current && typeof current.precipitation === "number"
    ? current.precipitation
    : 0;
  elMeasured.textContent = `${mm.toFixed(1)} mm`;
}

function renderFlood(loc, v) {
  const zone = nearestZone(loc.lat, loc.lon, ZONES);
  const fr = floodRisk(v.peakMm, zone);
  if (fr.level === "low") {
    elFloodRow.hidden = true;
    return;
  }
  elFlood.textContent = `⚠ ${fr.reason}`;
  elFlood.className = fr.level;
  elFloodRow.hidden = false;
}

function renderFooter() {
  elHonesty.textContent = `calibrated forecast for your spot · model v${MODEL.version}`;
}

async function render(loc) {
  const token = ++reqToken;
  activeLoc = loc;
  setState("state-loading");
  elVerdict.textContent = "Reading the sky…";
  elSub.textContent = "";

  try {
    const data = await fetchWeather(loc.lat, loc.lon);
    if (token !== reqToken) return; // a newer request superseded this one

    const fc = shapeForecast(data);
    const v = verdict(MODEL, fc, fc.nowHour, fc.recentRain);

    renderVerdict(v);
    renderLeave(v);
    renderMeasured(data.current);
    renderFlood(loc, v);
    rain.setIntensity(v.peakMm);
  } catch (err) {
    if (token !== reqToken) return;
    setState("state-error");
    elVerdict.textContent = "Can't reach the forecast";
    elSub.textContent = "Check your connection and tap your area to retry.";
    elLeave.hidden = true;
    elFloodRow.hidden = true;
    rain.setIntensity(0);
    console.error(err);
  }
}

// --- Location resolution ---
function nearestLocality(lat, lon) {
  let best = LOCALITIES[0];
  let bestD = Infinity;
  for (const l of LOCALITIES) {
    const d = (l.lat - lat) ** 2 + (l.lon - lon) ** 2;
    if (d < bestD) { bestD = d; best = l; }
  }
  return best;
}

function selectLocality(loc) {
  const idx = LOCALITIES.findIndex((l) => l.name === loc.name);
  if (idx >= 0) sel.value = String(idx);
}

// Try the browser's geolocation; on denial/timeout fall back to first locality.
function resolveAndRender() {
  if (!navigator.geolocation) {
    render(LOCALITIES[0]);
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const here = nearestLocality(pos.coords.latitude, pos.coords.longitude);
      // Use the user's real coords for accuracy, label with the nearest area.
      const loc = { name: here.name, lat: pos.coords.latitude, lon: pos.coords.longitude };
      selectLocality(here);
      render(loc);
    },
    () => render(LOCALITIES[0]),
    { timeout: 8000, maximumAge: 600000 }
  );
}

// --- Rain canvas: a calm/heavy curtain driven by predicted peak mm/h ---
const rain = (() => {
  const canvas = document.getElementById("rain");
  const ctx = canvas.getContext("2d");
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let drops = [];
  let target = 0;   // desired drop count
  let raf = null;
  let w = 0, h = 0, dpr = 1;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth = window.innerWidth;
    h = canvas.clientHeight = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function makeDrop() {
    return {
      x: Math.random() * w,
      y: Math.random() * -h,
      len: 8 + Math.random() * 14,
      spd: 4 + Math.random() * 6,
    };
  }

  function sync() {
    while (drops.length < target) drops.push(makeDrop());
    if (drops.length > target) drops.length = target;
  }

  function frame() {
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(127,184,196,0.35)"; // --monsoon, translucent
    ctx.lineWidth = 1;
    for (const d of drops) {
      ctx.beginPath();
      ctx.moveTo(d.x, d.y);
      ctx.lineTo(d.x, d.y + d.len);
      ctx.stroke();
      d.y += d.spd;
      if (d.y > h) { d.y = Math.random() * -40; d.x = Math.random() * w; }
    }
    raf = requestAnimationFrame(frame);
  }

  // Map peak mm/h to a drop count: 0 = clear, ~6mm = heavy sheets.
  function setIntensity(peakMm) {
    target = Math.round(Math.min(peakMm, 6) / 6 * 240);
    sync();
    if (reduceMotion) {
      // Draw a single static frame instead of animating.
      cancelAnimationFrame(raf);
      raf = null;
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = "rgba(127,184,196,0.30)";
      for (const d of drops) {
        ctx.beginPath();
        ctx.moveTo(d.x, d.y < 0 ? -d.y : d.y);
        ctx.lineTo(d.x, (d.y < 0 ? -d.y : d.y) + d.len);
        ctx.stroke();
      }
      return;
    }
    if (target > 0 && !raf) frame();
    if (target === 0 && raf) { cancelAnimationFrame(raf); raf = null; ctx.clearRect(0, 0, w, h); }
  }

  resize();
  window.addEventListener("resize", () => { resize(); sync(); });
  return { setIntensity };
})();

// --- Boot ---
async function init() {
  try {
    [ZONES, LOCALITIES, MODEL] = await Promise.all([
      json("data/flood-zones.json"),
      json("data/localities.json"),
      json("model.json"),
    ]);
  } catch (err) {
    setState("state-error");
    elVerdict.textContent = "Couldn't load app data";
    console.error(err);
    return;
  }

  // Populate the locality dropdown.
  LOCALITIES.forEach((l, i) => sel.add(new Option(l.name, String(i))));

  // Manual override always uses the locality's own coordinates.
  sel.addEventListener("change", () => render(LOCALITIES[Number(sel.value)]));

  renderFooter();
  resolveAndRender();
}

init();
