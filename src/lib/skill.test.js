// Unit tests for the calibration / contingency maths behind the scoreboard.
// Run with `bun test`.

import { test, expect } from "bun:test";
import { reliabilityBins, contingencyScores } from "./skill.js";

// ── reliabilityBins ─────────────────────────────────────────────────────────

test("a perfectly calibrated forecast sits on the diagonal", () => {
  // 10 forecasts at 0.9, nine of which rain -> observed 0.9 in the top bin.
  const probs = Array(10).fill(0.9);
  const actual = [1, 1, 1, 1, 1, 1, 1, 1, 1, 0];

  const top = reliabilityBins(probs, actual).at(-1);

  expect(top.n).toBe(10);
  expect(top.forecast).toBeCloseTo(0.9, 10);
  expect(top.observed).toBeCloseTo(0.9, 10);
});

test("an over-confident forecast shows observed below forecast", () => {
  // Says 0.8 ten times, only rains twice.
  const probs = Array(10).fill(0.8);
  const actual = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0];

  const bin = reliabilityBins(probs, actual).find((b) => b.n > 0);

  expect(bin.forecast).toBeCloseTo(0.8, 10);
  expect(bin.observed).toBeCloseTo(0.2, 10);
  expect(bin.observed).toBeLessThan(bin.forecast);
});

test("empty bins report null rather than zero", () => {
  // A zero observed frequency and "nothing landed here" must not look alike.
  const bins = reliabilityBins([0.05], [0]);

  expect(bins[0].n).toBe(1);
  expect(bins[0].observed).toBe(0);
  expect(bins[5].n).toBe(0);
  expect(bins[5].observed).toBeNull();
  expect(bins[5].forecast).toBeNull();
});

test("p = 1 lands in the top bin, not off the end", () => {
  const bins = reliabilityBins([1], [1]);

  expect(bins.at(-1).n).toBe(1);
  expect(bins.reduce((s, b) => s + b.n, 0)).toBe(1);
});

test("p = 0 lands in the first bin", () => {
  const bins = reliabilityBins([0], [0]);

  expect(bins[0].n).toBe(1);
});

test("every observation is counted exactly once", () => {
  const probs = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1];
  const actual = [0, 0, 1, 0, 1, 1, 1];

  const bins = reliabilityBins(probs, actual);

  expect(bins.reduce((s, b) => s + b.n, 0)).toBe(probs.length);
});

test("bin edges tile [0,1] with no gap or overlap", () => {
  const bins = reliabilityBins([], [], 5);

  expect(bins).toHaveLength(5);
  expect(bins[0].lo).toBe(0);
  expect(bins.at(-1).hi).toBe(1);
  for (let i = 1; i < bins.length; i++) expect(bins[i].lo).toBe(bins[i - 1].hi);
});

test("non-finite probabilities are skipped, not binned as 0", () => {
  const bins = reliabilityBins([NaN, 0.95], [1, 1]);

  expect(bins.reduce((s, b) => s + b.n, 0)).toBe(1);
  expect(bins[0].n).toBe(0);
});

test("bin count is configurable", () => {
  expect(reliabilityBins([], [], 5)).toHaveLength(5);
  expect(() => reliabilityBins([], [], 0)).toThrow(RangeError);
});

// ── contingencyScores ───────────────────────────────────────────────────────

test("a textbook confusion matrix gives the textbook scores", () => {
  // 8 rain hours: 6 caught, 2 missed. 10 rain calls: 6 right, 4 wrong.
  const s = contingencyScores({ tp: 6, fp: 4, fn: 2, tn: 88 });

  expect(s.pod).toBeCloseTo(6 / 8, 10);
  expect(s.far).toBeCloseTo(4 / 10, 10);
  expect(s.csi).toBeCloseTo(6 / 12, 10);
  expect(s.bias).toBeCloseTo(10 / 8, 10);
});

test("a perfect forecast scores POD 1, FAR 0, CSI 1, bias 1", () => {
  const s = contingencyScores({ tp: 5, fp: 0, fn: 0, tn: 20 });

  expect(s.pod).toBe(1);
  expect(s.far).toBe(0);
  expect(s.csi).toBe(1);
  expect(s.bias).toBe(1);
});

test("bias separates over- from under-forecasting", () => {
  expect(contingencyScores({ tp: 5, fp: 5, fn: 0, tn: 10 }).bias).toBeCloseTo(2, 10);
  expect(contingencyScores({ tp: 5, fp: 0, fn: 5, tn: 10 }).bias).toBeCloseTo(0.5, 10);
});

test("zero denominators give null, never NaN", () => {
  // Never rained in the holdout: POD and bias are undefined, not zero.
  const noRain = contingencyScores({ tp: 0, fp: 3, fn: 0, tn: 40 });
  expect(noRain.pod).toBeNull();
  expect(noRain.bias).toBeNull();
  expect(noRain.far).toBe(1);

  // Never called rain: FAR is undefined.
  const noCalls = contingencyScores({ tp: 0, fp: 0, fn: 4, tn: 40 });
  expect(noCalls.far).toBeNull();
  expect(noCalls.pod).toBe(0);

  // Nothing happened at all.
  const empty = contingencyScores({ tp: 0, fp: 0, fn: 0, tn: 0 });
  expect(empty.pod).toBeNull();
  expect(empty.far).toBeNull();
  expect(empty.csi).toBeNull();
  expect(empty.bias).toBeNull();
});

test("CSI ignores correct-dry hours, unlike accuracy", () => {
  // Same rain performance, wildly different dry counts: CSI must not move.
  const a = contingencyScores({ tp: 3, fp: 2, fn: 1, tn: 10 });
  const b = contingencyScores({ tp: 3, fp: 2, fn: 1, tn: 100_000 });

  expect(a.csi).toBe(b.csi);
});
