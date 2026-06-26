// nowcast.js — apply the exported model (model.json) to a live Open-Meteo
// forecast and reduce it to a single next-Nh verdict. Pure functions only,
// so this file is reused verbatim by the unit tests.
//
// Serving parity with pipeline/train.py:
//   FEATURE_NAMES = ["fc_bestmatch_mm", "fc_ecmwf_mm", "hour_sin", "hour_cos", "recent_rain_mm"]
//   row_to_features -> [bm, ec, sin(2πh/24), cos(2πh/24), recent_rain_mm]
//   predict_proba   -> sigmoid(intercept + Σ w·x)   (model "type": "logistic")
// rowFeatures + predict below mirror that EXACT order and arithmetic.

const RAIN_THRESHOLD_MM = 0.3; // mm/h ~ "noticeable drizzle"; linear-model rain cutoff.
const RAIN_PROB = 0.5;         // logistic-model rain cutoff (probability of rain).
const HORIZON_HRS = 2;         // default window; verdict() accepts an override.

// Feature vector in the EXACT order pipeline/train.py FEATURE_NAMES expects:
//   [fc_bestmatch_mm, fc_ecmwf_mm, hour_sin, hour_cos, recent_rain_mm]
// (best_match first, then the ECMWF benchmark — matches row_to_features.)
export function rowFeatures({ fc_bestmatch_mm, fc_ecmwf_mm, hour, recent_rain_mm }) {
  return [
    fc_bestmatch_mm,
    fc_ecmwf_mm,
    Math.sin((2 * Math.PI * hour) / 24),
    Math.cos((2 * Math.PI * hour) / 24),
    recent_rain_mm,
  ];
}

// Numerically-stable logistic, clamped like train.py's sigmoid (±60).
function sigmoid(z) {
  const c = Math.max(-60, Math.min(60, z));
  return 1 / (1 + Math.exp(-c));
}

// Apply the model by type:
//   logistic -> probability of rain in [0,1]  (sigmoid(intercept + Σ w·x))
//   else     -> linear corrector in mm, clamped >= 0 (rain can't be negative)
// The shared core is z = intercept + Σ w·x; only the squashing differs.
export function predict(model, feats) {
  const z =
    model.intercept + model.weights.reduce((s, w, i) => s + w * feats[i], 0);
  if (model.type === "logistic") return sigmoid(z);
  return Math.max(0, z);
}

// Roll the model across the next `horizonHrs` forecast hours and summarise.
// Returns { willRain, startsInHrs, endsInHrs, stillRaining, peakMm, prob, type, horizon }:
//   - willRain:     true if rain is called within the window.
//   - startsInHrs:  0 = raining this hour, 1 = next hour, … null if dry.
//   - endsInHrs:    offset (h) when the first rain block goes dry again, or null
//                   if it's still raining at the end of the window.
//   - stillRaining: true if rain is called but never stops within the window
//                   (so the UI says "through the next Nh", not a fake end time).
//   - peakMm:       highest rain intensity (mm/h) in the window, one decimal.
//                   For a logistic model — which emits a probability, not mm —
//                   this is the peak forecast best_match rate (the honest
//                   intensity reading the verdict can show).
//   - prob:         peak rain probability for logistic models, else null.
//   - type:         "logistic" | "linear".
//   - horizon:      the window (hours) actually evaluated.
// `horizonHrs` defaults to HORIZON_HRS so existing callers/tests are unchanged;
// the UI passes the user-chosen window (1/2/3/6h) so timing copy stays honest.
export function verdict(model, forecast, nowHour, recentRain, horizonHrs = HORIZON_HRS) {
  const isLogistic = model.type === "logistic";
  let startsInHrs = null;
  let endsInHrs = null; // first dry hour after rain begins (the "till when")
  let peakMm = 0;   // intensity reading (mm/h)
  let peakProb = 0; // logistic confidence
  const horizon = Math.min(horizonHrs, forecast.valid_at.length);

  for (let i = 0; i < horizon; i++) {
    const bm = forecast.fc_bestmatch_mm[i] ?? 0;
    const out = predict(
      model,
      rowFeatures({
        fc_bestmatch_mm: bm,
        fc_ecmwf_mm: forecast.fc_ecmwf_mm[i] ?? 0,
        hour: (nowHour + i) % 24,
        recent_rain_mm: recentRain,
      })
    );

    let raining;
    if (isLogistic) {
      peakProb = Math.max(peakProb, out);
      // Model gives probability, not mm — read intensity off the raw forecast.
      peakMm = Math.max(peakMm, bm);
      raining = out >= RAIN_PROB;
    } else {
      peakMm = Math.max(peakMm, out);
      raining = out >= RAIN_THRESHOLD_MM;
    }
    if (raining && startsInHrs === null) startsInHrs = i;
    // First dry hour after rain has begun closes the first block — that's the
    // "till when". Only the first block: rain can flicker back later in a long
    // window, and a nowcast shouldn't promise the gap is the end of everything.
    if (startsInHrs !== null && endsInHrs === null && !raining) endsInHrs = i;
  }

  const willRain = startsInHrs !== null;
  return {
    willRain,
    startsInHrs,
    endsInHrs,
    stillRaining: willRain && endsInHrs === null,
    peakMm: Math.round(peakMm * 10) / 10,
    prob: isLogistic ? Math.round(peakProb * 100) / 100 : null,
    type: isLogistic ? "logistic" : "linear",
    horizon,
  };
}
