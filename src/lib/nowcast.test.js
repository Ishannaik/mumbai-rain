// Unit tests for the pure verdict logic. Run with `bun test`.
//
// The fixture uses a LINEAR pass-through model (weights [1,0,0,0,0], intercept 0)
// so predict() returns the raw best_match mm — i.e. "raining when mm >= 0.3"
// (RAIN_THRESHOLD_MM). That isolates the rain-BLOCK detection (start/end) we're
// testing here from the model arithmetic, which has its own parity contract.

import { test, expect } from "bun:test";
import { verdict, predict, rowFeatures } from "./nowcast.js";

// Build a forecast object shaped like the live Open-Meteo parse: only the fields
// verdict() reads. fc_ecmwf is zeroed (the linear model ignores it via weight 0).
function fc(bm) {
  return {
    valid_at: bm.map((_, i) => i),
    fc_bestmatch_mm: bm,
    fc_ecmwf_mm: bm.map(() => 0),
  };
}

const LINEAR = { weights: [1, 0, 0, 0, 0], intercept: 0 };
const NOW = 12; // arbitrary current hour; rain-block logic is hour-agnostic

test("raining now, eases mid-window -> endsInHrs marks the first dry hour", () => {
  const v = verdict(LINEAR, fc([1, 1, 0, 0]), NOW, 0, 4);
  expect(v.willRain).toBe(true);
  expect(v.startsInHrs).toBe(0);
  expect(v.endsInHrs).toBe(2);     // dry again at +2h
  expect(v.stillRaining).toBe(false);
});

test("raining now, never stops in window -> endsInHrs null, stillRaining true", () => {
  const v = verdict(LINEAR, fc([1, 1, 1, 1]), NOW, 0, 4);
  expect(v.startsInHrs).toBe(0);
  expect(v.endsInHrs).toBe(null);  // end is beyond the horizon — unknown, not faked
  expect(v.stillRaining).toBe(true);
});

test("dry all window -> no start, no end, not still raining", () => {
  const v = verdict(LINEAR, fc([0, 0, 0, 0]), NOW, 0, 4);
  expect(v.willRain).toBe(false);
  expect(v.startsInHrs).toBe(null);
  expect(v.endsInHrs).toBe(null);
  expect(v.stillRaining).toBe(false);
});

test("rain incoming then ends -> start and end are both offsets", () => {
  const v = verdict(LINEAR, fc([0, 0, 1, 1, 0, 0]), NOW, 0, 6);
  expect(v.startsInHrs).toBe(2);
  expect(v.endsInHrs).toBe(4);     // duration = 4 - 2 = 2h
  expect(v.stillRaining).toBe(false);
});

test("only the FIRST rain block's end is reported (intermittent)", () => {
  // rain 0..1, dry at 2, rain again 3 -> first block ends at +2h
  const v = verdict(LINEAR, fc([1, 1, 0, 1]), NOW, 0, 4);
  expect(v.startsInHrs).toBe(0);
  expect(v.endsInHrs).toBe(2);
});

test("threshold: 0.2mm is dry, >=0.3mm is rain", () => {
  const v = verdict(LINEAR, fc([0.2, 1, 0]), NOW, 0, 3);
  expect(v.startsInHrs).toBe(1);   // 0.2 < 0.3 dry, 1.0 rains
  expect(v.endsInHrs).toBe(2);
});

test("logistic model gets the same start/end treatment", () => {
  // sigmoid(5*bm - 1): bm=1 -> 0.98 (rain, >=0.5); bm=0 -> 0.27 (dry)
  const LOGISTIC = { type: "logistic", weights: [5, 0, 0, 0, 0], intercept: -1 };
  const v = verdict(LOGISTIC, fc([1, 1, 0]), NOW, 0, 3);
  expect(v.startsInHrs).toBe(0);
  expect(v.endsInHrs).toBe(2);
  expect(v.prob).toBeGreaterThanOrEqual(0.5);
});

// Sanity: the pure model arithmetic still matches the parity contract.
test("predict() linear branch clamps negatives to 0", () => {
  expect(predict(LINEAR, rowFeatures({ fc_bestmatch_mm: -5, fc_ecmwf_mm: 0, hour: 0, recent_rain_mm: 0 }))).toBe(0);
});
