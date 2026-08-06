// पाऊस — Mumbai Rain · service worker (dependency-free, no build step).
// Offline-first app shell + last-forecast fallback. Bump CACHE to ship new assets;
// the activate handler then evicts every older cache.
//
// ROBUSTNESS (paus-v2): HTML navigations are NETWORK-FIRST so a bad/stale
// scoreboard bake ("Couldn't read the log") can never stick in cache-first
// forever. Static assets stay cache-first.

const CACHE = "paus-v2";

// Only stable, path-addressable URLs are precached. Astro's hashed JS/CSS bundles
// are NOT listed here (their names change every build) — they are picked up at
// runtime by the cache-first handler below, so no build hash is ever hardcoded.
const PRECACHE = ["/", "/data/localities.json", "/model.json", "/metrics.json"];

// Live data endpoints — network-first so a fresh reading always wins, while the
// last successful response is kept so the most recent forecast still shows offline.
const NETWORK_FIRST_HOSTS = ["api.open-meteo.com", "air-quality-api.open-meteo.com"];

// Same-origin paths that must never be stuck on a stale HTML/JSON snapshot.
// Scoreboard + metrics change with every data push; cache-first hid failures.
const NETWORK_FIRST_PATHS = ["/scoreboard", "/metrics.json", "/model.json"];

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
  // Take over ASAP so clients leave paus-v1 (cache-first HTML) behind.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
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

  if (url.origin !== self.location.origin) {
    // Cross-origin fonts, etc. — browser default.
    return;
  }

  // HTML documents + honesty-critical JSON → always prefer network.
  // This is the fix for "randomly seeing Couldn't read the log": that page was
  // a failed build cached forever under cache-first.
  const isNavigate = req.mode === "navigate";
  const acceptsHtml = (req.headers.get("accept") || "").includes("text/html");
  const isNetworkPath = NETWORK_FIRST_PATHS.some(
    (p) => url.pathname === p || url.pathname.startsWith(p + "/")
  );
  if (isNavigate || acceptsHtml || isNetworkPath) {
    event.respondWith(networkFirst(req));
    return;
  }

  // Hashed static assets (JS/CSS/images) → cache-first.
  event.respondWith(cacheFirst(req));
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
    const res = await fetch(req, { cache: "no-cache" });
    if (res && res.status === 200) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const cached = await cache.match(req);
    if (cached) return cached;
    // Offline navigation: fall back to home shell if we have it.
    if (req.mode === "navigate") {
      const shell = await caches.match("/");
      if (shell) return shell;
    }
    throw err;
  }
}
