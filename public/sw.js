// पाऊस — Mumbai Rain · service worker (dependency-free, no build step).
// Offline-first app shell + last-forecast fallback. Bump CACHE to ship new assets;
// the activate handler then evicts every older cache.

const CACHE = "paus-v1";

// Only stable, path-addressable URLs are precached. Astro's hashed JS/CSS bundles
// are NOT listed here (their names change every build) — they are picked up at
// runtime by the cache-first handler below, so no build hash is ever hardcoded.
const PRECACHE = ["/", "/data/localities.json", "/model.json"];

// Live data endpoints — network-first so a fresh reading always wins, while the
// last successful response is kept so the most recent forecast still shows offline.
const NETWORK_FIRST_HOSTS = ["api.open-meteo.com", "air-quality-api.open-meteo.com"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Add individually (not cache.addAll, which is atomic) and swallow misses so
      // one not-yet-built URL can't fail the whole install. "reload" bypasses the
      // HTTP cache so we precache the freshest copy.
      Promise.all(
        PRECACHE.map((url) =>
          cache.add(new Request(url, { cache: "reload" })).catch(() => {})
        )
      )
    )
  );
  // Intentionally no skipWaiting(): an updated worker waits until existing tabs
  // close, so a page is never served a half-old / half-new asset set mid-session.
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      // Safe to claim: with no skipWaiting this only runs once the old worker is
      // gone, and it lets the very first install control the open page immediately.
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return; // never touch mutations

  const url = new URL(req.url);

  // Live weather / air-quality APIs → network-first with cached fallback.
  if (NETWORK_FIRST_HOSTS.includes(url.hostname)) {
    event.respondWith(networkFirst(req));
    return;
  }

  // Same-origin GETs → cache-first, runtime-caching anything new (hashed bundles).
  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirst(req));
  }
  // Everything else (cross-origin fonts, etc.) falls through to the network as-is.
});

async function cacheFirst(req) {
  const cached = await caches.match(req);
  if (cached) return cached;
  try {
    const res = await fetch(req);
    // Only cache complete, same-origin 200s (skip 206 partials / opaque responses).
    if (res && res.status === 200 && res.type === "basic") {
      const copy = res.clone();
      caches.open(CACHE).then((cache) => cache.put(req, copy));
    }
    return res;
  } catch (err) {
    // Offline with nothing cached: serve the precached shell for navigations.
    if (req.mode === "navigate") {
      const shell = await caches.match("/");
      if (shell) return shell;
    }
    throw err;
  }
}

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res && res.status === 200) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const cached = await cache.match(req);
    if (cached) return cached;
    throw err; // truly offline and never fetched before → let the page handle it
  }
}
