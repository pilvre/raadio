// Salvestuste nimekiri (rec/*.json + pooleli live/*.json) ja kustutamine.
import { listJson } from "../../lib/audio.js";

const LIVE_STALE_MS = 10 * 60e3;

export async function onRequestGet({ env }) {
  const [done, live] = await Promise.all([listJson(env, "rec/"), listJson(env, "live/")]);
  const doneKeys = new Set(done.map((r) => r.key.slice(4)));
  const now = Date.now();
  // pooleli: ainult värsked ja need, millel valmis faili veel pole
  const inProgress = live.filter((r) => now - Date.parse(r.updated) < LIVE_STALE_MS && !doneKeys.has(r.key.slice(5)));
  const items = [...done, ...inProgress];
  // uuemad päevad eespool, päeva sees kronoloogiliselt (tunniosad järjest)
  const day = (iso) => new Date(iso).toLocaleDateString("sv-SE", { timeZone: "Europe/Tallinn" });
  items.sort((a, b) => day(b.start).localeCompare(day(a.start)) || a.start.localeCompare(b.start));
  const locked = new Set(await lockedKeys(env));
  for (const r of items) r.locked = locked.has(r.key);
  return Response.json(items, { headers: { "cache-control": "no-store" } });
}

// 🔒 lukustatud salvestust automaatne koristus ei kustuta (locked.json – sama mis recorder/webserver.py)
async function lockedKeys(env) {
  const obj = await env.KUKU.get("locked.json");
  return obj ? (await obj.json()).keys || [] : [];
}
async function setLocked(env, key, on) {
  const keys = new Set(await lockedKeys(env));
  on ? keys.add(key) : keys.delete(key);
  await env.KUKU.put("locked.json", JSON.stringify({ keys: [...keys].sort() }), { httpMetadata: { contentType: "application/json" } });
}

export async function onRequestPut({ env, request }) {
  const url = new URL(request.url), key = url.searchParams.get("key") || "";
  if (!/^rec\/[\w.-]+\.mp3$/.test(key)) return new Response("bad key", { status: 400 });
  const on = url.searchParams.get("locked") !== "0";
  await setLocked(env, key, on);
  return Response.json({ key, locked: on });
}

export async function onRequestDelete({ env, request }) {
  const key = new URL(request.url).searchParams.get("key") || "";
  if (!/^rec\/[\w.-]+\.mp3$/.test(key)) return new Response("bad key", { status: 400 });
  await env.KUKU.delete([key, key.replace(/\.mp3$/, ".json")]);
  await setLocked(env, key, false);
  return new Response(null, { status: 204 });
}
