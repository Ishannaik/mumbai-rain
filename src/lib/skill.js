// Calibration and contingency metrics for the holdout scoreboard.
//
// Brier alone hides miscalibration: a model that always says 30% on a 30%-rain
// climate scores well while being useless for a decision. These two answer the
// questions Brier cannot — "when we say 70%, does it rain ~70%?" (reliability)
// and "at the p >= 0.5 button-press, what do we hit and miss?" (contingency).
//
// Pure functions with no I/O so the scoreboard build and `bun test` share one
// implementation. Run with `bun test`.

/**
 * Bin forecast probabilities and compare mean forecast to observed frequency.
 *
 * A perfectly calibrated model has `observed ≈ forecast` in every populated bin;
 * that is the diagonal a reliability diagram plots against.
 *
 * @param {number[]} probs   forecast probabilities in [0, 1]
 * @param {number[]} actual  matching outcomes, 1 = it rained, 0 = it did not
 * @param {number}   nBins   number of equal-width bins (default 10)
 * @returns {{lo:number, hi:number, n:number, forecast:number|null,
 *            observed:number|null}[]} one row per bin, low edge ascending
 */
export function reliabilityBins(probs, actual, nBins = 10) {
  if (nBins < 1) throw new RangeError("nBins must be >= 1");

  const bins = Array.from({ length: nBins }, (_, i) => ({
    lo: i / nBins,
    hi: (i + 1) / nBins,
    n: 0,
    sumForecast: 0,
    sumObserved: 0,
  }));

  const n = Math.min(probs.length, actual.length);
  for (let i = 0; i < n; i++) {
    const p = probs[i];
    if (!Number.isFinite(p)) continue;
    // Clamp so p == 1 lands in the top bin rather than falling off the end.
    const idx = Math.min(nBins - 1, Math.max(0, Math.floor(p * nBins)));
    const bin = bins[idx];
    bin.n++;
    bin.sumForecast += p;
    bin.sumObserved += actual[i] === 1 ? 1 : 0;
  }

  return bins.map((b) => ({
    lo: b.lo,
    hi: b.hi,
    n: b.n,
    forecast: b.n ? b.sumForecast / b.n : null,
    observed: b.n ? b.sumObserved / b.n : null,
  }));
}

/**
 * Contingency scores at a decision threshold, from a 2x2 confusion matrix.
 *
 * - `pod`  probability of detection (hit rate): of the times it rained, how
 *          often did we call it? TP / (TP + FN)
 * - `far`  false alarm ratio: of the times we called rain, how often were we
 *          wrong? FP / (TP + FP)
 * - `csi`  critical success index (threat score), which unlike accuracy is not
 *          flattered by the many correct-dry hours: TP / (TP + FP + FN)
 * - `bias` frequency bias: how often we call rain vs how often it rains.
 *          1 = right on average, > 1 = over-forecasting. (TP + FP) / (TP + FN)
 *
 * Each is null when its denominator is zero, rather than 0 or NaN — "never
 * rained in the holdout" is a different statement from "we detected nothing".
 *
 * @param {{tp:number, fp:number, fn:number, tn:number}} m
 * @returns {{pod:number|null, far:number|null, csi:number|null, bias:number|null}}
 */
export function contingencyScores({ tp, fp, fn, tn }) {
  const observedRain = tp + fn;
  const calledRain = tp + fp;
  const csiDenom = tp + fp + fn;
  void tn; // present for completeness; none of these four scores use it

  return {
    pod: observedRain > 0 ? tp / observedRain : null,
    far: calledRain > 0 ? fp / calledRain : null,
    csi: csiDenom > 0 ? tp / csiDenom : null,
    bias: observedRain > 0 ? calledRain / observedRain : null,
  };
}
