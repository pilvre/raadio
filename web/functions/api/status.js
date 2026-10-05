export async function onRequestGet({ env }) {
  const obj = await env.KUKU.get("status.json");
  return Response.json(obj ? await obj.json() : null, { headers: { "cache-control": "no-store" } });
}
