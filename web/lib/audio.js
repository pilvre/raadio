// MP3 R2-st, Range toega (kerimine). Kasutavad /audio/* ja /feed/<võti>/audio/*.
export async function serveAudio(env, request, key, { download } = {}) {
  if (!/^(rec|live)\/[\w.-]+\.mp3$/.test(key)) return new Response("not found", { status: 404 });
  const live = key.startsWith("live/");
  const range = request.headers.get("range");
  const obj = request.method === "HEAD" ? await env.KUKU.head(key) : await env.KUKU.get(key, range ? { range: request.headers } : {});
  if (!obj) return new Response("not found", { status: 404 });
  const headers = new Headers({
    "content-type": "audio/mpeg",
    "accept-ranges": "bytes",
    "cache-control": live ? "no-store" : "private, max-age=86400",
    etag: obj.httpEtag,
  });
  if (download) {
    const name = download.replace(/[\\/:*?"<>|]+/g, " ").trim().slice(0, 120) || key.split("/").pop();
    headers.set("content-disposition", `attachment; filename*=UTF-8''${encodeURIComponent(name)}`);
  }
  if (request.method === "HEAD") {
    headers.set("content-length", String(obj.size));
    return new Response(null, { headers });
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

export async function listJson(env, prefix) {
  const keys = [];
  let cursor;
  do {
    const page = await env.KUKU.list({ prefix, cursor });
    keys.push(...page.objects.map((o) => o.key).filter((k) => k.endsWith(".json")));
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return (await Promise.all(keys.map(async (k) => (await env.KUKU.get(k))?.json()))).filter(Boolean);
}
