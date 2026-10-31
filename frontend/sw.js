const CACHE = "sentinel-v1";
const ASSETS = [
  "/", "/worker", "/admin",
  "/static/auth.js", "/static/worker.js", "/static/admin.js",
  "/static/manifest.webmanifest", "/static/icon.svg"
];

self.addEventListener("install", function(event) {
  event.waitUntil(
    caches.open(CACHE).then(function(cache) {
      return cache.addAll(ASSETS).catch(function() {});
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(keys.filter(function(k) { return k !== CACHE; }).map(function(k) { return caches.delete(k); }));
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function(event) {
  if (event.request.method !== "GET") return;
  const url = event.request.url;
  if (url.includes("/api/") || url.includes("/auth/")) return;

  event.respondWith(
    fetch(event.request).then(function(response) {
      if (response.ok) {
        const clone = response.clone();
        caches.open(CACHE).then(function(cache) { cache.put(event.request, clone); });
      }
      return response;
    }).catch(function() {
      return caches.match(event.request).then(function(r) {
        return r || caches.match("/");
      });
    })
  );
});
