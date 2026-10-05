// Salvestusvalikud (config.json R2-s), loeb ja kirjutab ka Maci salvestaja.
//   shows:    [{id, name, station, reruns, keep}]   – "salvesta kõik saated"
//   episodes: [{id, station, start, end, title, rerun, description, show, auto}]
//             – konkreetsed ajad; auto = brauser koostas saate tellimuse põhjal (ERR)
//   timers:   [{id, station, name, days[0..6], start "HH:MM", end "HH:MM", keep, enabled}]
// keep = mitu viimast episoodi alles hoida (null = vaikimisi 14 päeva)
const str = (x, n = 300) => String(x ?? "").slice(0, n);
const keepOf = (k) => (k ? Math.max(1, Math.min(50, Math.round(+k))) : null);
const normId = (id) => (String(id).includes(":") ? String(id) : `kuku:${id}`);
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

export async function onRequestGet({ env }) {
  const obj = await env.KUKU.get("config.json");
  const config = obj ? await obj.json() : {};
  return Response.json({ shows: [], episodes: [], timers: [], ...config }, { headers: { "cache-control": "no-store" } });
}

export async function onRequestPut({ env, request }) {
  const body = await request.json();
  const now = Date.now();
  const config = {
    shows: (body.shows || []).map((s) => ({
      id: normId(s.id), name: str(s.name), station: str(s.station || normId(s.id).split(":")[0], 40),
      reruns: !!s.reruns, keep: keepOf(s.keep),
    })),
    // möödunud episoodid koristatakse ära
    episodes: (body.episodes || [])
      .filter((e) => Date.parse(e.end) > now)
      .map((e) => ({
        id: normId(e.id), station: str(e.station || "kuku", 40),
        start: str(e.start, 40), end: str(e.end, 40), title: str(e.title), rerun: !!e.rerun,
        description: str(e.description, 500),
        show: e.show ? { id: normId(e.show.id), name: str(e.show.name), description: str(e.show.description, 300),
          thumbnail: e.show.thumbnail ? str(e.show.thumbnail, 500) : null } : undefined,
        auto: !!e.auto,
      })),
    timers: (body.timers || [])
      .filter((t) => /^timer:[\w-]{1,40}$/.test(t.id) && HHMM.test(t.start) && HHMM.test(t.end))
      .map((t) => ({
        id: t.id, station: str(t.station, 40), name: str(t.name || "Taimer", 80),
        days: [...new Set((t.days || []).map(Number).filter((d) => d >= 0 && d <= 6))].sort(),
        start: t.start, end: t.end, keep: keepOf(t.keep), enabled: t.enabled !== false,
      })),
    synced: Object.fromEntries(Object.entries(body.synced || {}).map(([k, v]) => [str(k, 40), str(v, 40)])),
    updated: new Date().toISOString(),
  };
  await env.KUKU.put("config.json", JSON.stringify(config, null, 1), {
    httpMetadata: { contentType: "application/json" },
  });
  return Response.json(config);
}
