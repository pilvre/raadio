#!/usr/bin/env python3
"""Raadiosalvestaja (Kuku, ERR-i jaamad, ...).

Loeb R2-st config.json (mida veebiliides muudab), võrdleb seda jaamade saatekavaga
ja salvestab valitud saated otse-eetrist mono-MP3-na. Ühtlustatud kava kirjutatakse
R2-sse (schedule.json), veebiliides loeb seda. Valmis fail + metaandmed
laetakse R2 bucketisse (rec/...). Iga tsükli järel kirjutatakse status.json,
et veebiliides näeks, kas salvestaja on elus.
"""

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import certifi

from storage import make_storage

STATIONS_FILE = Path(__file__).resolve().parent.parent / "web" / "stations.json"
KUKU_SCHEDULE_URL = "https://ams.postimees.ee/api/schedule?domain=kuku.pleier.ee&start={start}&end={end}"
ERR_SCHEDULE_URL = "https://vikerraadio.err.ee/api/radioSchedule/getTimelineSchedule2?day={d}&month={m}&year={y}&channel={channel}&portal=radio"
SCHEDULE_DAYS = 7

PRE_ROLL = timedelta(minutes=1)    # alusta varem
POST_ROLL = timedelta(minutes=2)   # lõpeta hiljem
OVERLAP = timedelta(seconds=30)    # tunniosade kattuvus
MIN_PART = timedelta(minutes=15)   # lühem jupp liidetakse naabriga
POLL_SECONDS = 20                  # lühike, et tunniosade kattuvus (30 s) püsiks
SCHEDULE_TTL = timedelta(minutes=30)
APP_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = APP_ROOT / "VERSION"          # olemas ainult avalikust repost paigaldatud koopias
UPDATE_URL = "https://raadio.mastering.ee/version.json"
UPDATE_EVERY = timedelta(hours=12)


def local_version():
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None  # arenduskoopia (git) – uuendusi ei kontrollita
BITRATE = "64k"
KEEP_DAYS = 14                     # vaikimisi säilitus (kui saatel pole "keep")
CLEANUP_EVERY = timedelta(minutes=30)
LIVE_EVERY = 120                   # pooleli faili üleslaadimise intervall (s)

STATE_DIR = Path.home() / ".local" / "share" / "kuku-salvestus"
CONF_DIRS = [Path.home() / ".config" / "raadiosalvestaja", Path.home() / ".config" / "kuku-salvestus"]
CONF_DIR = CONF_DIRS[0]
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
# Windowsis taustal (pythonw) ei tohi ffmpeg konsooliakent avada
NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
# config.env (uus) või r2.env (vana nimi); puudumisel kohalik režiim vaikeseadetega
def find_conf():
    if os.environ.get("RAADIO_CONF"):
        return Path(os.environ["RAADIO_CONF"])
    for d in CONF_DIRS:
        for name in ("config.env", "r2.env"):  # r2.env = vana nimi
            if (d / name).exists():
                return d / name
    return CONF_DIR / "config.env"


CRED_FILE = find_conf()
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load_env(path):
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "saade"


def parse_ts(s):
    return datetime.fromisoformat(s)


def norm_id(x):
    """Vanad (numbrilised) Kuku ID-d -> "kuku:123"."""
    return x if isinstance(x, str) and ":" in x else f"kuku:{x}"


def strip_html(s, limit=400):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "raadiosalvestaja/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return json.load(r)


# --- kava adapterid: tagastavad ühtlustatud episoodid -----------------------
# {id, station, start, end, title, rerun, description, show: {id, name, description, thumbnail}}

def fetch_kuku(st, now):
    url = KUKU_SCHEDULE_URL.format(
        start=(now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        end=(now + timedelta(days=SCHEDULE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    out = []
    for day in http_json(url):
        for e in day["episodes"]:
            if parse_ts(e["end"]) <= parse_ts(e["start"]):
                continue  # uudiste jms markerid
            sh = e["show"]
            out.append({
                "id": f"{st['id']}:{e['id']}", "station": st["id"],
                "start": e["start"], "end": e["end"], "title": e["title"],
                "rerun": bool(e.get("rerun_for")),
                "description": strip_html(e.get("description")) or sh.get("description_short") or "",
                "show": {
                    "id": f"{st['id']}:{sh['id']}", "name": sh["name"],
                    "description": sh.get("description_short") or "",
                    "thumbnail": (sh.get("thumbnail") or {}).get("square_250_x1"),
                },
            })
    return out


# Serveripoolne kava ainult jaamadele, kus see on lubatud. ERR-i kava on Cloudflare'i
# robotikaitse taga – selle laeb veebiliides kasutaja brauseris ja kirjutab valitud
# saated konkreetsete aegadena config.json-i (episodes).
FETCHERS = {"kuku": fetch_kuku}
WEEKDAYS = "ETKNRLP"


def expand_timers(timers, now):
    """Taimer {id, station, name, days:[0..6], start:"HH:MM", end:"HH:MM"} -> episoodid (eile..+2 p)."""
    out = []
    today = now.astimezone().date()
    for t in timers:
        if not t.get("enabled", True):
            continue
        sh, sm = map(int, t["start"].split(":"))
        eh, em = map(int, t["end"].split(":"))
        for off in range(-1, 3):
            day = today + timedelta(days=off)
            if day.weekday() not in t.get("days", []):
                continue
            start = datetime(day.year, day.month, day.day, sh, sm).astimezone()
            end = datetime(day.year, day.month, day.day, eh, em).astimezone()
            if end <= start:
                end += timedelta(days=1)  # üle südaöö
            out.append({
                "id": f"{t['id']}@{day.isoformat()}", "station": t["station"],
                "start": start.isoformat(), "end": end.isoformat(),
                "title": f"{t['name']} {day:%d.%m.%Y}", "rerun": False, "description": "",
                "show": {"id": t["id"], "name": t["name"], "description": "", "thumbnail": None},
            })
    return out



def hhmm(t):
    t = t.astimezone()
    return f"{t:%H}" if t.minute == 0 else f"{t:%H:%M}"


def split_hours(ep):
    """Üle tunni pikk saade -> täistundide kaupa osad (06–07, 07–08, ...)."""
    start, end = parse_ts(ep["start"]), parse_ts(ep["end"])
    if end - start <= timedelta(hours=1):
        return [ep]
    bounds = [start]
    t = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while t < end:
        bounds.append(t)
        t += timedelta(hours=1)
    bounds.append(end)
    # liiga lühikesed otsad naabriga kokku
    if len(bounds) > 2 and bounds[1] - bounds[0] < MIN_PART:
        bounds.pop(1)
    if len(bounds) > 2 and bounds[-1] - bounds[-2] < MIN_PART:
        bounds.pop(-2)
    n = len(bounds) - 1
    parts = []
    for i in range(n):
        a, b = bounds[i], bounds[i + 1]
        seg = dict(ep)
        seg.update({
            "start": a.isoformat(), "end": b.isoformat(),
            "title": f"{ep['title']} · {hhmm(a)}–{hhmm(b)}",
            "part": i + 1, "parts": n,
            "episode_start": ep["start"], "episode_end": ep["end"],
            "_pre": PRE_ROLL if i == 0 else OVERLAP,
            "_post": POST_ROLL if i == n - 1 else OVERLAP,
        })
        parts.append(seg)
    return parts


def lan_address():
    """Aadress, millega telefon samas võrgus ligi pääseb: Macis <nimi>.local, mujal IP."""
    import socket
    if sys.platform == "darwin":
        try:
            name = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=3).stdout.strip()
            if name:
                return name + ".local"
        except Exception:
            pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # ei saada midagi, ainult valib väljuva liidese
            return s.getsockname()[0]
    except Exception:
        return socket.gethostname()


def setup_log_file(path):
    """Taustateenusena (nt Windowsi pythonw) logi faili; suur fail roteeritakse."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 5_000_000:
        path.replace(path.with_suffix(path.suffix + ".1"))
    f = open(path, "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = f


class Recorder:
    def __init__(self):
        global KUKU_SCHEDULE_URL
        global FFMPEG
        env = load_env(CRED_FILE)
        FFMPEG = env.get("FFMPEG") or FFMPEG
        self.stations = {st["id"]: st for st in json.loads(STATIONS_FILE.read_text(encoding="utf-8"))}
        if env.get("KUKU_STREAM_URL"):
            self.stations["kuku"]["stream"] = env["KUKU_STREAM_URL"]
        KUKU_SCHEDULE_URL = env.get("KUKU_SCHEDULE_URL") or KUKU_SCHEDULE_URL
        self.env = env
        self.store = make_storage(env)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.done_file = STATE_DIR / "done.json"
        self.done = set(json.loads(self.done_file.read_text(encoding="utf-8"))) if self.done_file.exists() else set()
        self.active = {}  # key -> info dict
        self.lock = threading.Lock()
        self.schedule = []
        self.by_station = {}  # jaam -> viimati edukalt laetud episoodid
        self.schedule_at = None
        self.last_error = None
        self.config = {}
        self.meta_cache = {}  # rec/*.json võti -> metaandmed
        self.cleanup_lock = threading.Lock()
        self.cleanup_at = None
        self.version = local_version()
        self.update = None        # {"latest", "date", "notes"} kui uuem versioon on saadaval
        self.update_at = None
        self.salvage_lock = threading.Lock()

    # --- salvestuskiht (R2 või kohalik kaust) ----------------------------
    def get_json(self, key, default):
        return self.store.get_json(key, default)

    def put_json(self, key, data):
        self.store.put_json(key, data)

    # --- kava -------------------------------------------------------------
    def refresh_schedule(self):
        now = datetime.now(timezone.utc)
        if self.schedule_at and now - self.schedule_at < SCHEDULE_TTL:
            return
        for sid, st in self.stations.items():
            if st["schedule"]["type"] not in FETCHERS:
                continue
            try:
                self.by_station[sid] = FETCHERS[st["schedule"]["type"]](st, now)
            except Exception as e:
                log(f"kava viga ({st['name']}): {e}")  # jääb eelmine kava
        lo, hi = now - timedelta(hours=6), now + timedelta(days=SCHEDULE_DAYS)
        self.schedule = sorted(
            (ep for eps in self.by_station.values() for ep in eps
             if parse_ts(ep["end"]) > lo and parse_ts(ep["start"]) < hi),
            key=lambda ep: (ep["start"], ep["station"]),
        )
        self.schedule_at = now
        self.put_json("schedule.json", {
            "updated": now.isoformat(),
            "stations": [{k: st[k] for k in ("id", "name", "short")} for st in self.stations.values()],
            "server_stations": sorted(self.by_station),
            "episodes": self.schedule,
        })
        log(f"kava uuendatud: {len(self.schedule)} saadet, {len(self.by_station)} jaama")

    def wanted(self, config):
        """Salvestatavad episoodid: Kuku kava × saated, config.episodes (valmis ajad), taimerid."""
        shows = {norm_id(s["id"]): s for s in config.get("shows", [])}
        sched = {ep["id"]: ep for ep in self.schedule}
        seen = set()

        def emit(ep):
            if ep["id"] not in seen and ep["station"] in self.stations:
                seen.add(ep["id"])
                return True
            return False

        for ep in self.schedule:
            s = shows.get(ep["show"]["id"])
            if s and (not ep["rerun"] or s.get("reruns")) and emit(ep):
                yield ep
        for e in config.get("episodes", []):
            ep = sched.get(norm_id(e["id"]))
            if ep is None and e.get("station") and e.get("show"):
                ep = e  # brauseris koostatud (nt ERR) – ajad on kaasas
            if ep and emit(ep):
                yield ep
        for ep in expand_timers(config.get("timers", []), datetime.now(timezone.utc)):
            if emit(ep):
                yield ep

    # --- salvestamine -----------------------------------------------------
    def record(self, key, ep):
        start, end = parse_ts(ep["start"]), parse_ts(ep["end"])
        stop_at = end + ep.get("_post", POST_ROLL)
        show = ep["show"]
        station = self.stations[ep["station"]]
        tmp = Path(tempfile.mkdtemp(prefix="kuku-"))
        parts = []
        name = f"{start.astimezone():%Y-%m-%d_%H%M}_{station['id']}_{slugify(show['name'])}"
        base = f"rec/{name}"
        live_base = f"live/{name}"

        def make_meta(prefix, duration, size, **extra):
            return {
                "key": prefix + ".mp3",
                "episode_id": ep["id"],
                "title": ep["title"],
                "station": station["id"],
                "station_name": station["name"],
                "show_id": show["id"],
                "show": show["name"],
                "description": ep.get("description") or show.get("description") or "",
                "thumbnail": show.get("thumbnail"),
                "start": ep["start"],
                "end": ep["end"],
                "rerun": bool(ep.get("rerun")),
                "part": ep.get("part"),
                "parts": ep.get("parts"),
                "episode_start": ep.get("episode_start", ep["start"]),
                "episode_end": ep.get("episode_end", ep["end"]),
                "duration": duration,
                "size": size,
                **extra,
            }

        def upload_live(current):
            # pooleli salvestus: senised osad + jooksev fail baitide kaupa kokku (MP3 talub seda)
            live = tmp / "live.mp3"
            with open(live, "wb") as f:
                for p in parts + [current]:
                    if p.exists():
                        f.write(p.read_bytes())
            size = live.stat().st_size
            self.store.put_file(live, live_base + ".mp3")
            self.put_json(live_base + ".json", make_meta(
                live_base, int(size * 8 / 64000), size,
                live=True, updated=datetime.now(timezone.utc).isoformat(),
            ))

        last_live = time.time()
        try:
            self.salvage(live_base)  # sama osa eelmine katkenud katse, kui on
            log(f"START {ep['title']} ({ep['start'][11:16]}–{ep['end'][11:16]})")
            n = 0
            while True:
                remaining = (stop_at - datetime.now(timezone.utc)).total_seconds()
                if remaining < 5:
                    break
                part = tmp / f"part{n:03d}.mp3"
                n += 1
                cmd = [
                    FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-reconnect", "1", "-reconnect_streamed", "1",
                    "-reconnect_on_network_error", "1", "-reconnect_delay_max", "10",
                    "-rw_timeout", "20000000",
                    *(["-live_start_index", "-1"] if ".m3u8" in station["stream"] else []),
                    "-i", station["stream"],
                    # Kuku voog on sisuliselt mono (L=R) ja juba 0 dBFS peal; -ac 1 liidaks
                    # kanalid +3 dB-ga ja klipiks. Keskmistame ja jätame ~1 dB varu MP3 jaoks.
                    "-vn", "-af", "pan=mono|c0=0.45*c0+0.45*c1",
                    "-c:a", "libmp3lame", "-b:a", BITRATE,
                    "-write_xing", "0",
                    str(part),
                ]
                # lõpp määratakse kella järgi (mitte -t), sest HLS-i ajatemplid hüppavad
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **NO_WINDOW)
                # valvur: kui fail 90 s ei kasva, tapa ja alusta uuesti
                last_size, last_change = -1, time.time()
                while proc.poll() is None:
                    time.sleep(2)
                    if datetime.now(timezone.utc) >= stop_at:
                        try:
                            proc.stdin.write("q")
                            proc.stdin.flush()
                            proc.wait(timeout=15)
                        except Exception:
                            proc.kill()
                        break
                    size = part.stat().st_size if part.exists() else 0
                    if size != last_size:
                        last_size, last_change = size, time.time()
                    elif time.time() - last_change > 90:
                        log(f"  voog seiskus, taaskäivitan ({ep['title']})")
                        proc.kill()
                        break
                    with self.lock:
                        self.active[key]["bytes"] = sum(p.stat().st_size for p in parts) + size
                    if time.time() - last_live > LIVE_EVERY and size > 0:
                        last_live = time.time()
                        try:
                            upload_live(part)
                        except Exception as e:
                            log(f"  pooleli faili üleslaadimine ebaõnnestus: {e}")
                proc.wait()
                if part.exists() and part.stat().st_size > 0:
                    parts.append(part)
                if proc.returncode not in (0, None):
                    err = (proc.stderr.read() or "").strip()[-300:]
                    log(f"  ffmpeg lõpetas koodiga {proc.returncode}: {err}")
                    time.sleep(5)

            if not parts:
                raise RuntimeError("salvestus jäi tühjaks")

            out = tmp / "out.mp3"
            if len(parts) == 1:
                shutil.move(parts[0], out)
            else:
                lst = tmp / "list.txt"
                lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
                subprocess.run(
                    [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                     "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
                    check=True, **NO_WINDOW,
                )

            duration = self.probe_duration(out)
            meta = make_meta(base, duration, out.stat().st_size,
                             recorded_at=datetime.now(timezone.utc).isoformat())
            self.store.put_file(out, meta["key"])
            self.put_json(base + ".json", meta)
            log(f"VALMIS {meta['key']} ({meta['size'] // 1024} KB, {duration // 60} min)")
            self.cleanup()
        except Exception as e:
            self.last_error = f"{ep['title']}: {e}"
            log("VIGA", self.last_error)
            traceback.print_exc()
        finally:
            try:
                self.store.delete([live_base + ".mp3", live_base + ".json"])
            except Exception:
                pass
            shutil.rmtree(tmp, ignore_errors=True)
            with self.lock:
                self.active.pop(key, None)
                self.done.add(key)
                self.done_file.write_text(json.dumps(sorted(self.done)[-500:]), encoding="utf-8")

    @staticmethod
    def probe_duration(path):
        r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True, **NO_WINDOW)
        m = re.search(r"Duration: (\d+):(\d+):(\d+)", r.stderr)
        return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) if m else 0

    # --- katkenud salvestuste päästmine ----------------------------------
    def exists(self, key):
        return self.store.exists(key)

    def salvage(self, live_base, min_age=None):
        """Pooleli (live/) fail, mille kirjutaja suri -> tavaline salvestus sildiga "katkestatud"."""
        with self.salvage_lock:
            meta = self.get_json(live_base + ".json", None)
            if not meta or not self.exists(live_base + ".mp3"):
                return
            if min_age and datetime.now(timezone.utc) - parse_ts(meta["updated"]) < min_age:
                return
            name = live_base.split("/", 1)[1]
            dest, i = f"rec/{name}-katkestus", 1
            while self.exists(dest + ".mp3"):
                i += 1
                dest = f"rec/{name}-katkestus{i}"
            self.store.copy(live_base + ".mp3", dest + ".mp3")
            meta.pop("live", None)
            meta.update(key=dest + ".mp3", incomplete=True, recorded_at=meta.pop("updated", None))
            self.put_json(dest + ".json", meta)
            self.store.delete([live_base + ".mp3", live_base + ".json"])
            log(f"PÄÄSTETUD katkenud salvestus -> {dest}.mp3 ({meta['duration'] // 60} min)")

    # --- koristus -------------------------------------------------------
    def cleanup(self):
        """Saatel "keep": N -> alles N viimast valmis episoodi; muidu KEEP_DAYS päeva."""
        if not self.cleanup_lock.acquire(blocking=False):
            return
        try:
            for k, _ in self.store.list("live/"):
                if k.endswith(".json"):
                    self.salvage(k[:-5], min_age=timedelta(seconds=LIVE_EVERY * 2.5))
            keys = [k for k, _ in self.store.list("rec/") if k.endswith(".json")]
            self.meta_cache = {k: self.meta_cache.get(k) or self.get_json(k, None) for k in keys}
            metas = [m for m in self.meta_cache.values() if m]

            now = datetime.now(timezone.utc)
            shows = {norm_id(s["id"]): s for s in self.config.get("shows", [])}
            shows.update({t["id"]: t for t in self.config.get("timers", [])})
            keep_days = int(self.config.get("keep_days") or KEEP_DAYS)
            # episood = saate üks saatepäev (nt Vikerhommik 05:30–09:00 + 09:15–10:05 on üks)
            episodes = {}  # (show_id, kohalik kuupäev) -> [meta]
            for m in metas:
                day = parse_ts(m.get("episode_start", m["start"])).astimezone().date().isoformat()
                episodes.setdefault((norm_id(m.get("show_id")), day), []).append(m)

            doomed = []
            by_show = {}
            for (sid, ep_start), parts in episodes.items():
                keep = (shows.get(sid) or {}).get("keep")
                if keep:
                    by_show.setdefault(sid, []).append((ep_start, parts))
                elif now - max(parse_ts(p["start"]) for p in parts) > timedelta(days=keep_days):
                    doomed += parts
            for sid, eps in by_show.items():
                keep = int(shows[sid]["keep"])
                complete = 0
                for ep_start, parts in sorted(eps, key=lambda e: e[0], reverse=True):
                    ep_end = max(parse_ts(p.get("episode_end", p["end"])) for p in parts)
                    if ep_end + POST_ROLL + timedelta(minutes=3) > now:
                        continue  # pooleli episood ei loe veel
                    complete += 1
                    if complete > keep:
                        doomed += parts

            for m in doomed:
                k = m["key"]
                self.store.delete([k, k[:-4] + ".json"])
                self.meta_cache.pop(k[:-4] + ".json", None)
                log(f"kustutatud {k}")
            self.cleanup_at = now
        except Exception as e:
            log("koristuse viga:", e)
        finally:
            self.cleanup_lock.release()

    def check_update(self):
        """Kord 12 h jooksul: kas raadio.mastering.ee-l on uuem versioon? (UPDATE_CHECK=0 lülitab välja)"""
        if not self.version or self.env.get("UPDATE_CHECK") == "0":
            return
        try:
            info = http_json(self.env.get("UPDATE_URL") or UPDATE_URL)
            latest = str(info.get("version") or "")
            self.update = ({"latest": latest, "date": info.get("date"), "notes": info.get("notes")}
                           if latest and latest != self.version else None)
            if self.update:
                log(f"uuendus saadaval: {self.version} → {latest} (raadio update)")
        except Exception as e:
            log(f"uuenduste kontroll ebaõnnestus: {e}")

    def tick(self):
        config = self.config = self.get_json("config.json", {})
        self.refresh_schedule()
        if self.version and (not self.update_at or datetime.now(timezone.utc) - self.update_at >= UPDATE_EVERY):
            self.update_at = datetime.now(timezone.utc)  # järgmine tsükkel ei käivita uut kontrolli
            threading.Thread(target=self.check_update, daemon=True).start()
        if not self.cleanup_at or datetime.now(timezone.utc) - self.cleanup_at > CLEANUP_EVERY:
            threading.Thread(target=self.cleanup, daemon=True).start()
        now = datetime.now(timezone.utc)
        upcoming = []
        for ep in (seg for e in self.wanted(config) for seg in split_hours(e)):
            start, end = parse_ts(ep["start"]), parse_ts(ep["end"])
            key = f"{ep['id']}@{ep['start']}"
            if end <= now or key in self.done:
                continue
            if start - ep.get("_pre", PRE_ROLL) <= now:
                with self.lock:
                    if key in self.active:
                        continue
                    self.active[key] = {"title": ep["title"], "start": ep["start"], "end": ep["end"], "bytes": 0}
                threading.Thread(target=self.record, args=(key, ep), daemon=True).start()
            else:
                upcoming.append({"title": ep["title"], "start": ep["start"], "end": ep["end"]})
        upcoming.sort(key=lambda x: x["start"])
        with self.lock:
            recording = list(self.active.values())
        self.put_json("status.json", {
            "updated": now.isoformat(),
            "recording": recording,
            "next": upcoming[:5],
            "last_error": self.last_error,
            "version": self.version,
            "update": self.update,
        })

    def start_web(self):
        """Kohalikus režiimis (või WEB=1) jagab arvuti ise veebilehte ja API-t."""
        if self.store.kind != "local" and self.env.get("WEB") != "1":
            return
        import webserver
        port = int(self.env.get("WEB_PORT") or 8788)
        auth = (self.env.get("WEB_USER") or "raadio", self.env["WEB_PASS"]) if self.env.get("WEB_PASS") else None
        webserver.start(self.store, port=port, auth=auth)
        # aadressi leidmine võib aeglane olla – ära hoia käivitust kinni
        threading.Thread(target=lambda: log(f"veebileht: http://{lan_address()}:{port}"
                                            + ("" if auth else "  (parool puudub – ainult koduvõrgus!)")), daemon=True).start()

    @staticmethod
    def kill_orphans():
        """Windows: eelmise (kokku jooksnud) protsessi ffmpeg-id jäävad ellu – lõpeta need."""
        if sys.platform != "win32":
            return
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe'\" | "
                        "Where-Object { $_.CommandLine -like '*write_xing*' } | "
                        "Invoke-CimMethod -MethodName Terminate | Out-Null"], capture_output=True, **NO_WINDOW)

    def run(self):
        self.kill_orphans()
        log(f"salvestaja käivitus ({self.store.kind}: {getattr(self.store, 'root', None) or getattr(self.store, 'bucket', '')})")
        self.start_web()
        while True:
            try:
                self.tick()
            except Exception as e:
                self.last_error = str(e)
                log("tsükli viga:", e)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    if "--test" in sys.argv:
        # kiirtest: salvesta N s (vaikimisi 60) ja lae üles
        secs = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        r = Recorder()
        now = datetime.now(timezone.utc).astimezone()
        ep = {
            "id": 0, "title": f"Test {now:%d-%m-%Y %H:%M}",
            "start": now.isoformat(), "end": (now + timedelta(seconds=secs) - POST_ROLL).isoformat(),
            "station": sys.argv[3] if len(sys.argv) > 3 else "kuku", "rerun": False, "description": "Testsalvestus",
            "show": {"id": "test:0", "name": "Test", "description": "Testsalvestus", "thumbnail": None},
        }
        r.active["test"] = {"title": ep["title"], "bytes": 0}
        r.record("test", ep)
    else:
        env = load_env(CRED_FILE)
        if env.get("LOG_FILE"):
            setup_log_file(env["LOG_FILE"])
        Recorder().run()
