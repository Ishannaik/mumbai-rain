// Map tiles + India geocode. Run with `bun test`.
//
// Break: Carto basemaps watermarking "API KEY REQUIRED", or a geocode
// that is not scoped to India.

import { test, expect } from "bun:test";
import { indiaGeocodeUrl, MAP_TILES } from "./geo.js";

test("map tiles are not Carto (those now watermark without a key)", () => {
  expect(MAP_TILES.url).not.toContain("cartocdn");
  expect(MAP_TILES.url).not.toContain("basemaps.carto");
  expect(MAP_TILES.url).toContain("{z}");
  expect(MAP_TILES.url).toContain("{x}");
  expect(MAP_TILES.url).toContain("{y}");
});

test("indiaGeocodeUrl scopes Open-Meteo search to India", () => {
  const url = indiaGeocodeUrl("Chennai");
  expect(url).toContain("geocoding-api.open-meteo.com");
  expect(url).toContain("country=IN");
  expect(url).toContain("name=Chennai");
});

test("indiaGeocodeUrl encodes spaces", () => {
  expect(indiaGeocodeUrl("New Delhi")).toContain("name=New%20Delhi");
});
