// Kogu leht (sh /api ja /audio) parooli taha. Kasutaja ja parool tulevad
// Pages saladustest AUTH_USER ja AUTH_PASS; kui need puuduvad, ei lasta kedagi sisse.
const enc = new TextEncoder();

async function same(a, b) {
  const [x, y] = await Promise.all([a, b].map((s) => crypto.subtle.digest("SHA-256", enc.encode(s))));
  return crypto.subtle.timingSafeEqual(x, y);
}

export async function onRequest({ request, env, next }) {
  // ainult lokaalseks arenduseks (.dev.vars), mitte kunagi Pages seadetes
  if (env.DEV_NO_AUTH === "1" && new URL(request.url).hostname === "localhost") return next();
  // podcasti-feed kontrollib ise salajast võtit (functions/feed)
  if (new URL(request.url).pathname.startsWith("/feed/")) return next();
  if (!env.AUTH_USER || !env.AUTH_PASS) {
    return new Response("AUTH_USER / AUTH_PASS pole seadistatud", { status: 503 });
  }
  const header = request.headers.get("authorization") || "";
  if (header.startsWith("Basic ")) {
    let decoded = "";
    try { decoded = atob(header.slice(6)); } catch {}
    const i = decoded.indexOf(":");
    if (i > 0 && (await same(decoded.slice(0, i), env.AUTH_USER)) && (await same(decoded.slice(i + 1), env.AUTH_PASS))) {
      return next();
    }
  }
  return new Response("Sisselogimine vajalik", {
    status: 401,
    headers: { "www-authenticate": 'Basic realm="Raadiosalvesti", charset="UTF-8"' },
  });
}
