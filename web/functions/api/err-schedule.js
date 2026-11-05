// ERR-i kava, mille kasutaja tõi ERR-i lehelt järjehoidjaga (ERR-i API ei luba teistelt saitidelt päringuid).
// Sama mis recorder/webserver.py → normalize_err_schedule.
import STATIONS from "../../stations.json";

const str = (x, n = 300) => String(x ?? "").slice(0, n);
const ERR_IDS = new Set(STATIONS.filter((s) => s.schedule.type === "err").map((s) => s.id));

export async function onRequestGet({ env }) {
  const obj = await env.KUKU.get("err_schedule.json");
  return Response.json(obj ? await obj.json() : { updated: null, episodes: [] }, { headers: { "cache-control": "no-store" } });
}

export async function onRequestPut({ env, request }) {
  if (+(request.headers.get("content-length") || 0) > 4_000_000) return new Response("liiga suur", { status: 413 });
  const body = await request.json();
  const episodes = (body.episodes || []).slice(0, 4000)
    .filter((e) => ERR_IDS.has(e.station) && Date.parse(e.end) > Date.parse(e.start))
    .map((e) => ({
      id: str(e.id, 80), station: e.station, start: str(e.start, 40), end: str(e.end, 40),
      title: str(e.title), rerun: !!e.rerun, description: str(e.description, 2000),
      show: { id: str(e.show?.id, 80), name: str(e.show?.name), description: "",
        thumbnail: e.show?.thumbnail ? str(e.show.thumbnail, 500) : null },
    }));
  const data = { updated: new Date().toISOString(), episodes };
  await env.KUKU.put("err_schedule.json", JSON.stringify(data), { httpMetadata: { contentType: "application/json" } });
  return Response.json({ updated: data.updated, count: episodes.length });
}
