// Jaamad + serveripoolne kava (salvestaja kirjutab R2-sse schedule.json).
// Jaamad, mille kava pole serveris (nt ERR), laeb brauser ise.
import STATIONS from "../../stations.json";

export async function onRequestGet({ env }) {
  const obj = await env.KUKU.get("schedule.json");
  const data = obj ? await obj.json() : { episodes: [], server_stations: [] };
  const stations = STATIONS.map(({ id, name, short, stream, schedule }) => ({
    id, name, short, stream, schedule: { type: schedule.type, channel: schedule.channel },
    server: (data.server_stations || []).includes(id),
  }));
  return Response.json(
    { stations, storage: "r2", updated: data.updated || null, episodes: data.episodes || [] },
    { headers: { "cache-control": "no-store" } },
  );
}
