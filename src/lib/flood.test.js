// Flood watch must not fire for a city hundreds of km from Mumbai hotspots.
// Run with `bun test`.

import { test, expect } from "bun:test";
import { nearestZone, floodRisk } from "./flood.js";

const ZONES = [
  { name: "Hindmata", lat: 19.0176, lon: 72.8430, severity: 3 },
  { name: "Bandra", lat: 19.0596, lon: 72.8295, severity: 2 },
];

test("Colaba still resolves to a Mumbai flood hotspot", () => {
  const z = nearestZone(18.9151, 72.8260, ZONES);
  expect(z).not.toBe(null);
  expect(z.name).toBe("Hindmata");
});

test("Chennai is too far for a Mumbai flood zone", () => {
  expect(nearestZone(13.0827, 80.2707, ZONES)).toBe(null);
});

test("Pune is too far for a Mumbai flood zone", () => {
  expect(nearestZone(18.5204, 73.8567, ZONES)).toBe(null);
});

test("no zone means no flood watch, even in heavy rain", () => {
  expect(floodRisk(20, null).level).toBe("low");
});
