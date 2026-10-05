// Offline-tugi: rakenduse kest + API viimane vastus + telefoni laaditud salvestused.
// Töötab ainult turvalises kontekstis (https või localhost).
const SHELL = "shell-v1";
const API = "api-v1";
const AUDIO = "audio-v1"; // leht kirjutab siia ise (⬇ Telefoni)

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(SHELL).then((c) => c.add("/")).catch(() => {}));
});
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin || e.request.method !== "GET") return; // ERR API, pildid, CDN: otse
  if (url.pathname.startsWith("/audio/")) return e.respondWith(audio(e.request, url));
  if (url.pathname.startsWith("/api/")) return e.respondWith(networkFirst(e.request, API));
  if (url.pathname === "/" || url.pathname === "/index.html") return e.respondWith(networkFirst(e.request, SHELL, "/"));
});

async function networkFirst(req, cacheName, key) {
  try {
    const res = await fetch(req);
    if (res.ok) (await caches.open(cacheName)).put(key || req, res.clone());
    return res;
  } catch {
    return (await caches.match(key || req)) || new Response("offline", { status: 503 });
  }
}

// Laaditud salvestus vahemälust, Range toega (pleieri kerimine)
async function audio(req, url) {
  if (url.searchParams.has("dl")) return fetch(req);
  const cached = await (await caches.open(AUDIO)).match(url.origin + url.pathname);
  if (!cached) return fetch(req);
  const blob = await cached.blob();
  const size = blob.size;
  const base = { "content-type": "audio/mpeg", "accept-ranges": "bytes" };
  const m = /bytes=(\d*)-(\d*)/.exec(req.headers.get("range") || "");
  if (!m) return new Response(blob, { headers: { ...base, "content-length": String(size) } });
  let start = m[1] ? +m[1] : Math.max(0, size - +m[2]);
  let end = m[1] && m[2] ? Math.min(+m[2], size - 1) : size - 1;
  if (start > end) return new Response(null, { status: 416, headers: { "content-range": `bytes */${size}` } });
  return new Response(blob.slice(start, end + 1), {
    status: 206,
    headers: { ...base, "content-length": String(end - start + 1), "content-range": `bytes ${start}-${end}/${size}` },
  });
}
