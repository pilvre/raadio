// Serveerib MP3 R2-st, Range-päringute toega (kerimine pleieris).
export async function onRequestGet({ env, request, params }) {
  const key = [].concat(params.path || []).join("/");
  if (!/^(rec|live)\/[\w.-]+\.mp3$/.test(key)) return new Response("not found", { status: 404 });
  const live = key.startsWith("live/");
  const range = request.headers.get("range");
  const obj = await env.KUKU.get(key, range ? { range: request.headers } : {});
  if (!obj) return new Response("not found", { status: 404 });
  const headers = new Headers({
    "content-type": "audio/mpeg",
    "accept-ranges": "bytes",
    "cache-control": live ? "no-store" : "private, max-age=86400",
    etag: obj.httpEtag,
  });
  const dl = new URL(request.url).searchParams.get("dl");
  if (dl) {
    const name = dl.replace(/[\\/:*?"<>|]+/g, " ").trim().slice(0, 120) || key.split("/").pop();
    headers.set("content-disposition", `attachment; filename*=UTF-8''${encodeURIComponent(name)}`);
  }
  if (range && obj.range) {
    let { offset, length, suffix } = obj.range;
    if (suffix !== undefined) offset = obj.size - suffix, length = suffix;
    offset ??= 0;
    length ??= obj.size - offset;
    headers.set("content-range", `bytes ${offset}-${offset + length - 1}/${obj.size}`);
    headers.set("content-length", String(length));
    return new Response(obj.body, { status: 206, headers });
  }
  headers.set("content-length", String(obj.size));
  return new Response(obj.body, { headers });
}
