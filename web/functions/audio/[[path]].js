// Serveerib MP3 R2-st (parooliga, vt _middleware.js)
import { serveAudio } from "../../lib/audio.js";

export const onRequestGet = ({ env, request, params }) =>
  serveAudio(env, request, [].concat(params.path || []).join("/"), { download: new URL(request.url).searchParams.get("dl") });
export const onRequestHead = onRequestGet;
