// Minimal shell cache: enough to install and to open offline.
// ponytail: no API caching on purpose — a stale run result would be a lie, and the
// posting and CV must never sit in a cache on a shared machine.
const CACHE = "gradpilot-shell-v1";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/favicon.svg", "/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/") || url.origin !== self.location.origin) return;

  // Network first so a deploy is picked up; cache is the offline fallback.
  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((c) => c.put(request, copy));
        return response;
      })
      .catch(() => caches.match(request).then((hit) => hit || caches.match("/index.html"))),
  );
});
