"""Kohalik veebiserver (kohalik režiim): sama API mis Cloudflare Pages Functions (web/functions).

Veebileht (web/public) on sama mõlemas režiimis. Andmed tulevad salvestuskihist (storage.py).
"""

import base64
import hmac
import json
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "web" / "public"
STATIONS_FILE = Path(__file__).resolve().parent.parent / "web" / "stations.json"
LIVE_STALE_S = 10 * 60
KEY_RE = re.compile(r"^(rec|live)/[\w.-]+\.mp3$")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".json": "application/json", ".css": "text/css", ".svg": "image/svg+xml",
         ".png": "image/png", ".webmanifest": "application/manifest+json"}


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def tallinn_day(iso):
    return parse_ts(iso).astimezone().date().isoformat()


# --- config.json normaliseerimine (sama mis web/functions/api/config.js) ----------------
def _s(x, n=300):
    return str("" if x is None else x)[:n]


def _keep(k):
    try:
        return max(1, min(50, round(float(k)))) if k else None
    except (TypeError, ValueError):
        return None


def _norm_id(i):
    return str(i) if ":" in str(i) else f"kuku:{i}"


def normalize_config(body):
    now = datetime.now(timezone.utc)
    eps = []
    for e in body.get("episodes") or []:
        try:
            if parse_ts(e["end"]) <= now:
                continue
        except Exception:
            continue
        sh = e.get("show")
        eps.append({
            "id": _norm_id(e["id"]), "station": _s(e.get("station") or "kuku", 40),
            "start": _s(e.get("start"), 40), "end": _s(e.get("end"), 40), "title": _s(e.get("title")),
            "rerun": bool(e.get("rerun")), "description": _s(e.get("description"), 500),
            **({"show": {"id": _norm_id(sh["id"]), "name": _s(sh.get("name")),
                         "description": _s(sh.get("description")),
                         "thumbnail": _s(sh["thumbnail"], 500) if sh.get("thumbnail") else None}} if sh else {}),
            "auto": bool(e.get("auto")),
        })
    timers = []
    for t in body.get("timers") or []:
        if not (re.fullmatch(r"timer:[\w-]{1,40}", str(t.get("id", ""))) and HHMM.match(str(t.get("start", "")))
                and HHMM.match(str(t.get("end", "")))):
            continue
        timers.append({
            "id": t["id"], "station": _s(t.get("station"), 40), "name": _s(t.get("name") or "Taimer", 80),
            "days": sorted({int(d) for d in t.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6}),
            "start": t["start"], "end": t["end"], "keep": _keep(t.get("keep")), "enabled": t.get("enabled") is not False,
        })
    return {
        "shows": [{"id": _norm_id(s["id"]), "name": _s(s.get("name")),
                   "station": _s(s.get("station") or _norm_id(s["id"]).split(":")[0], 40),
                   "reruns": bool(s.get("reruns")), "keep": _keep(s.get("keep"))} for s in body.get("shows") or []],
        "episodes": eps,
        "timers": timers,
        **({"feed_token": body["feed_token"]} if re.fullmatch(r"[\w-]{20,64}", str(body.get("feed_token") or "")) else {}),
        "synced": {_s(k, 40): _s(v, 40) for k, v in (body.get("synced") or {}).items()},
        "updated": now.isoformat(),
    }


# --- podcasti-feed (sama mis web/lib/feed.js) ---------------------------------------------
def _x(v):
    return (str("" if v is None else v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def show_slug(i):
    # vanad (enne mitut jaama) salvestused: show_id = 209 -> "kuku:209"
    i = "muu" if i is None else (str(i) if ":" in str(i) else f"kuku:{i}")
    return re.sub(r"[^\w-]+", "-", i)


def _hms(sec):
    sec = max(0, round(sec or 0))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def build_feed(recs, base, token, slug, name=None):
    from email.utils import format_datetime
    allf = slug == "koik"
    items = sorted((r for r in recs if r.get("key", "").startswith("rec/") and (allf or show_slug(r.get("show_id")) == slug)),
                   key=lambda r: r["start"], reverse=True)
    title = "Raadiosalvestaja" if allf else f"{items[0]['show'] if items else (name or 'Saade')} (Raadiosalvestaja)"
    image = None if allf else next((r["thumbnail"] for r in items if r.get("thumbnail")), None)
    out = []
    for r in items:
        st = parse_ts(r["start"])
        t = ((r["show"] + " · ") if allf else "") + st.astimezone().strftime("%d.%m.%Y %H:%M")
        if (r.get("parts") or 0) > 1:
            t += f" · osa {r['part']}/{r['parts']}"
        if r.get("incomplete"):
            t += " (katkestatud)"
        desc = " – ".join(v for v in (r.get("title"), r.get("station_name"), r.get("description")) if v)
        out.append(f"""<item>
  <title>{_x(t)}</title>
  <description>{_x(desc)}</description>
  <guid isPermaLink="false">{_x(r['key'])}</guid>
  <pubDate>{format_datetime(st.astimezone(timezone.utc), usegmt=True)}</pubDate>
  <enclosure url="{_x(f'{base}/feed/{token}/audio/{r["key"]}')}" length="{r.get('size') or 0}" type="audio/mpeg"/>
  <itunes:duration>{_hms(r.get('duration'))}</itunes:duration>""" + (f'\n  <itunes:image href="{_x(r["thumbnail"])}"/>' if r.get("thumbnail") else "") + "\n</item>")
    img = (f'\n<itunes:image href="{_x(image)}"/>\n<image><url>{_x(image)}</url><title>{_x(title)}</title><link>{_x(base)}</link></image>'
           if image else "")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>{_x(title)}</title>
<link>{_x(base)}</link>
<atom:link href="{_x(f'{base}/feed/{token}/{slug}.xml')}" rel="self" type="application/rss+xml"/>
<description>Isiklikud raadiosalvestused – privaatne feed, ära jaga.</description>
<language>et</language>
<itunes:block>Yes</itunes:block>
<itunes:explicit>false</itunes:explicit>{img}
{chr(10).join(out)}
</channel>
</rss>"""


def make_handler(store, auth):
    stations_def = json.loads(STATIONS_FILE.read_text(encoding="utf-8"))

    class Handler(BaseHTTPRequestHandler):
        server_version = "Raadiosalvestaja"

        def log_message(self, *a):  # vaikne
            pass

        # --- abi ---
        def send_json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_text(self, text, status):
            body = text.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if status == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="Raadiosalvestaja", charset="UTF-8"')
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            if not auth:
                return True
            h = self.headers.get("Authorization", "")
            if h.startswith("Basic "):
                try:
                    user, _, pw = base64.b64decode(h[6:]).decode().partition(":")
                    return hmac.compare_digest(user, auth[0]) & hmac.compare_digest(pw, auth[1])
                except Exception:
                    return False
            return False

        def route(self, method):
            url = urlparse(self.path)
            # podcasti-feed: salajane võti asendab parooli (ainult salvestused, mitte valikud)
            if url.path.startswith("/feed/") and method in ("GET", "HEAD"):
                try:
                    return self.feed(url, head=method == "HEAD")
                except BrokenPipeError:
                    return
            if not self.authorized():
                return self.send_text("Sisselogimine vajalik", 401)
            q = parse_qs(url.query)
            p = url.path
            try:
                if p == "/api/schedule" and method == "GET":
                    return self.api_schedule()
                if p == "/api/config":
                    if method == "GET":
                        return self.send_json({"shows": [], "episodes": [], "timers": [], **store.get_json("config.json", {})})
                    if method == "PUT":
                        n = int(self.headers.get("Content-Length") or 0)
                        cfg = normalize_config(json.loads(self.rfile.read(n) or b"{}"))
                        store.put_json("config.json", cfg)
                        return self.send_json(cfg)
                if p == "/api/status" and method == "GET":
                    return self.send_json(store.get_json("status.json", None))
                if p == "/api/recordings":
                    if method == "GET":
                        return self.api_recordings()
                    if method == "DELETE":
                        key = (q.get("key") or [""])[0]
                        if not re.fullmatch(r"rec/[\w.-]+\.mp3", key):
                            return self.send_text("bad key", 400)
                        store.delete([key, key[:-4] + ".json"])
                        self.send_response(204)
                        self.end_headers()
                        return
                if p.startswith("/audio/") and method in ("GET", "HEAD"):
                    return self.audio(p[len("/audio/"):], q, head=method == "HEAD")
                if method in ("GET", "HEAD"):
                    return self.static(p, head=method == "HEAD")
                return self.send_text("not found", 404)
            except BrokenPipeError:
                pass
            except Exception as e:
                try:
                    self.send_text(f"viga: {e}", 500)
                except Exception:
                    pass

        do_GET = lambda self: self.route("GET")
        do_HEAD = lambda self: self.route("HEAD")
        do_PUT = lambda self: self.route("PUT")
        do_DELETE = lambda self: self.route("DELETE")

        # --- API ---
        def api_schedule(self):
            data = store.get_json("schedule.json", None) or {"episodes": [], "server_stations": []}
            stations = [{"id": s["id"], "name": s["name"], "short": s.get("short"), "stream": s["stream"],
                         "schedule": {"type": s["schedule"]["type"], "channel": s["schedule"].get("channel")},
                         "server": s["id"] in (data.get("server_stations") or [])} for s in stations_def]
            self.send_json({"stations": stations, "updated": data.get("updated"), "episodes": data.get("episodes", [])})

        def api_recordings(self):
            done = [m for k, _ in store.list("rec/") if k.endswith(".json") and (m := store.get_json(k, None))]
            live = [m for k, _ in store.list("live/") if k.endswith(".json") and (m := store.get_json(k, None))]
            done_names = {m["key"][4:] for m in done}
            now = datetime.now(timezone.utc)
            items = done + [m for m in live if m.get("updated")
                            and (now - parse_ts(m["updated"])).total_seconds() < LIVE_STALE_S
                            and m["key"][5:] not in done_names]
            # uuemad päevad eespool, päeva sees kronoloogiliselt
            items.sort(key=lambda m: m["start"])
            items.sort(key=lambda m: tallinn_day(m["start"]), reverse=True)
            self.send_json(items)

        def audio(self, key, q, head=False):
            if not KEY_RE.match(key) or not store.exists(key):
                return self.send_text("not found", 404)
            path = store.path(key)
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
            if m and size:
                if m[1]:
                    start = int(m[1])
                    end = min(int(m[2]), size - 1) if m[2] else size - 1
                elif m[2]:
                    start = max(0, size - int(m[2]))
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-store" if key.startswith("live/") else "private, max-age=86400")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if q.get("dl"):
                name = re.sub(r'[\\/:*?"<>|]+', " ", q["dl"][0]).strip()[:120] or Path(key).name
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
            self.end_headers()
            if head:
                return
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def feed(self, url, head=False):
            parts = url.path.split("/")[2:]  # [token, ...]
            real = (store.get_json("config.json", {}) or {}).get("feed_token") or ""
            if not parts or not real or not hmac.compare_digest(parts[0], real):
                return self.send_text("not found", 404)
            token, rest = parts[0], parts[1:]
            if rest[:1] == ["audio"]:
                return self.audio("/".join(rest[1:]), {}, head=head)
            m = re.fullmatch(r"([\w-]+)\.xml", "/".join(rest))
            if not m:
                return self.send_text("not found", 404)
            host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "localhost"
            proto = self.headers.get("X-Forwarded-Proto") or ("https" if host.split(":")[0].endswith(".ts.net") else "http")
            recs = [mm for k, _ in store.list("rec/") if k.endswith(".json") and (mm := store.get_json(k, None))]
            cfg = store.get_json("config.json", {}) or {}
            named = next((s.get("name") for s in (cfg.get("shows") or []) + (cfg.get("timers") or []) if show_slug(s.get("id")) == m[1]), None)
            body = build_feed(recs, f"{proto}://{host}", token, m[1], named).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def static(self, p, head=False):
            rel = "index.html" if p in ("", "/") else p.lstrip("/")
            f = (PUBLIC_DIR / rel).resolve()
            if PUBLIC_DIR.resolve() not in f.parents or not f.is_file():
                return self.send_text("not found", 404)
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(f.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if not head:
                self.wfile.write(body)

    return Handler


def start(store, port=8788, auth=None, host="0.0.0.0"):
    srv = ThreadingHTTPServer((host, port), make_handler(store, auth))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="web").start()
    return srv
