// Keyless India place search + raster tiles for the pin-on-map picker.
// Carto Positron used to be free; it now watermarks "API KEY REQUIRED".
// OSM tiles + Open-Meteo geocoding (country=IN) stay $0 on the live path.

export const MAP_TILES = {
  url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: "&copy; OpenStreetMap",
  maxZoom: 19,
};

export function indiaGeocodeUrl(q) {
  return (
    "https://geocoding-api.open-meteo.com/v1/search" +
    `?name=${encodeURIComponent(q)}&count=6&language=en&format=json&countryCode=IN`
  );
}

export function indiaOnly(results) {
  return (results || []).filter((r) => r && r.country_code === "IN");
}
