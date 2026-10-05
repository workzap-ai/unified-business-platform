/*
 * pi service worker: makes the pi app and pi Customer installable and shows a friendly
 * page when the device is offline. Deliberately small and safe:
 *  - API calls (/api/...) are never touched: messages, chats and figures always come
 *    from the server.
 *  - Pages always come from the network; the offline page is only a fallback.
 *  - Only fingerprinted build files (/_next/static/) and the offline assets are cached.
 *  - A new version clears every older cache when it activates.
 */
const VERSION = "pi-pwa-v1";
const OFFLINE = "/offline.html";
const PRECACHE = [OFFLINE, "/brand/pi/pi-sorry-color.svg", "/icons/pi-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(VERSION)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/"))
    return;

  if (PRECACHE.includes(url.pathname)) {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request)),
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
    return;
  }

  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(VERSION).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
  }
});
