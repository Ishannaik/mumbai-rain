// Map tiles + India geocode. Run with `bun test`.
//
// Break: Carto basemaps watermarking "API KEY REQUIRED", or a geocode
// that is not scoped to India.

import { test, expect } from "bun:test";
import { indiaGeocodeUrl, MAP_TILES, indiaOnly } from "./geo.js";

test("map tiles are not Carto (those now watermark without a key)", () => {
  expect(MAP_TILES.url).not.toContain("cartocdn");
  expect(MAP_TILES.url).not.toContain("basemaps.carto");
  expect(MAP_TILES.url).toContain("{z}");
  expect(MAP_TILES.url).toContain("{x}");
  expect(MAP_TILES.url).toContain("{y}");
});

test("indiaGeocodeUrl uses countryCode=IN (country= is ignored by Open-Meteo)", () => {
  const url = indiaGeocodeUrl("Chennai");
  expect(url).toContain("geocoding-api.open-meteo.com");
  expect(url).toContain("countryCode=IN");
  expect(url).not.toContain("country=IN");
  expect(url).toContain("name=Chennai");
});

test("indiaGeocodeUrl encodes spaces", () => {
  expect(indiaGeocodeUrl("New Delhi")).toContain("name=New%20Delhi");
});

test("indiaOnly drops non-India geocode hits", () => {
  const kept = indiaOnly([
    { name: "Pune", country_code: "IN", admin1: "Maharashtra" },
    { name: "Pune", country_code: "TL", admin1: "Oecusse" },
    { name: "Pune", country_code: "BR", admin1: "Pará" },
  ]);
  expect(kept).toHaveLength(1);
  expect(kept[0].admin1).toBe("Maharashtra");
});
