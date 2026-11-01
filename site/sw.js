/* Free Military Benefits service worker.
   Network first for the page and data.json, so updates show on the next visit and the app still opens offline.
   zip.json and places.json are cached on first use and refreshed in the background.
   Only same-origin GET requests are handled; AI provider calls and map links are never cached.
   Bump VERSION whenever the SHELL list changes. */
const VERSION = "fmb-v0.7.0";
const SHELL = ["./", "index.html", "data.json", "manifest.webmanifest", "icon-192.png", "icon-512.png",
  "icon-maskable-512.png", "apple-touch-icon.png", "favicon-32.png"];
const BIG = ["zip.json", "places.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

function put(req, res) {
  if (res && res.ok && res.type === "basic") {
    const copy = res.clone();
    caches.open(VERSION).then((c) => c.put(req, copy));
  }
  return res;
}

async function networkFirst(req, waitMs) {
  const cached = caches.match(req, {ignoreSearch: true});
  const net = fetch(req).then((res) => put(req, res));
  const timer = new Promise((resolve) => setTimeout(resolve, waitMs, null));
  const first = await Promise.race([net.catch(() => null), timer]);
  if (first) return first;
  const hit = await cached;
  if (hit) return hit;
  return net; // nothing cached yet: wait for the network, or fail as the browser would
}

async function staleWhileRevalidate(req) {
  const hit = await caches.match(req, {ignoreSearch: true});
  const net = fetch(req).then((res) => put(req, res)).catch(() => null);
  return hit || (await net) || Response.error();
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const name = url.pathname.split("/").pop();
  if (req.mode === "navigate" || name === "" || name === "index.html") {
    event.respondWith(networkFirst(new Request(new URL("index.html", self.registration.scope)), 4000)); // one cached copy of the page
  } else if (name === "data.json") {
    event.respondWith(networkFirst(req, 4000));
  } else if (BIG.includes(name)) {
    event.respondWith(staleWhileRevalidate(req));
  } else {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => put(req, res))));
  }
});
