// nowcast.js — apply the exported model (model.json) to a live Open-Meteo
// forecast and reduce it to a single next-2h verdict. Pure functions only,
// so this file is reused verbatim by the unit tests.
//
// Serving parity: rowFeatures + predict mirror the Python training code
// (pipeline/features.py row_to_features, pipeline/train.py predict) exactly —
// same feature order, same cyclic hour encoding, same clamp at zero.

const RAIN_THRESHOLD_MM = 0.3; // mm/h ~ "noticeable drizzle"; below this we call it dry.
const HORIZON_HRS = 2;         // we only answer for the next 2 hours.

// Feature vector in the exact order model.json["features"] expects:
//   [fc_ecmwf_mm, fc_bestmatch_mm, hour_sin, hour_cos, recent_rain_mm]
export function rowFeatures({ fc_ecmwf_mm, fc_bestmatch_mm, hour, recent_rain_mm }) {
  return [
    fc_ecmwf_mm,
    fc_bestmatch_mm,
    Math.sin((2 * Math.PI * hour) / 24),
    Math.cos((2 * Math.PI * hour) / 24),
    recent_rain_mm,
  ];
}

// Linear corrector: intercept + sum(w*x), clamped to >= 0 (rain can't be negative).
export function predict(model, feats) {
  const p =
    model.intercept + model.weights.reduce((s, w, i) => s + w * feats[i], 0);
  return Math.max(0, p);
}

// Roll the model across the next HORIZON_HRS forecast hours and summarise.
// Returns { willRain, startsInHrs, peakMm }:
//   - startsInHrs: 0 = raining this hour, 1 = next hour, ... null if dry.
//   - peakMm: highest corrected mm/h seen in the window (one decimal).
export function verdict(model, forecast, nowHour, recentRain) {
  let startsInHrs = null;
  let peakMm = 0;
  const horizon = Math.min(HORIZON_HRS, forecast.valid_at.length);

  for (let i = 0; i < horizon; i++) {
    const mm = predict(
      model,
      rowFeatures({
        fc_ecmwf_mm: forecast.fc_ecmwf_mm[i] ?? 0,
        fc_bestmatch_mm: forecast.fc_bestmatch_mm[i] ?? 0,
        hour: (nowHour + i) % 24,
        recent_rain_mm: recentRain,
      })
    );
    peakMm = Math.max(peakMm, mm);
    if (mm >= RAIN_THRESHOLD_MM && startsInHrs === null) startsInHrs = i;
  }

  return {
    willRain: startsInHrs !== null,
    startsInHrs,
    peakMm: Math.round(peakMm * 10) / 10,
  };
}
