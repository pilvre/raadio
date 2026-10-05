// Privaatne podcasti-feed: /feed/<võti>/koik.xml, /feed/<võti>/<saade>.xml, /feed/<võti>/audio/rec/....mp3
// Võti (config.json: feed_token) asendab parooli – podcastirakendused ei oska alati sisse logida.
// Ligipääs ainult salvestustele, mitte valikutele ega kustutamisele.
import { serveAudio, listJson } from "../../lib/audio.js";
import { buildFeed } from "../../lib/feed.js";

async function tokenOk(env, token) {
  const cfg = await (await env.KUKU.get("config.json"))?.json();
  const real = cfg?.feed_token;
  if (!real || !token || real.length !== token.length) return false;
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([real, token].map((s) => crypto.subtle.digest("SHA-256", enc.encode(s))));
  return crypto.subtle.timingSafeEqual(a, b);
}

export async function onRequest({ env, request, params }) {
  if (!["GET", "HEAD"].includes(request.method)) return new Response(null, { status: 405 });
  const [token, ...rest] = [].concat(params.path || []);
  if (!(await tokenOk(env, token))) return new Response("not found", { status: 404 });
  if (rest[0] === "audio") return serveAudio(env, request, rest.slice(1).join("/"));
  const m = /^([\w-]+)\.xml$/.exec(rest.join("/"));
  if (!m) return new Response("not found", { status: 404 });
  const url = new URL(request.url);
  const xml = buildFeed(await listJson(env, "rec/"), { base: url.origin, token, slug: m[1] });
  return new Response(request.method === "HEAD" ? null : xml, {
    headers: { "content-type": "application/rss+xml; charset=utf-8", "cache-control": "no-store", "x-robots-tag": "noindex" },
  });
}
