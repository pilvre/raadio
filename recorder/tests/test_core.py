"""Kiired kontrollid, mis peavad töötama ka vanal Pythonil (macOS-i vaikimisi 3.9)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.argv = ["test"]
import kuku_recorder as k  # noqa: E402
import webserver as w  # noqa: E402


def test_parse_ts_browser_and_server_formats():
    for s in ["2026-10-05T02:30:00.000Z", "2026-10-11T12:57:10.822Z",
              "2026-10-06T10:00:00.000000+03:00", "2026-10-11T15:57:00+03:00"]:
        assert k.parse_ts(s) == w.parse_ts(s)
        assert k.parse_ts(s).tzinfo is not None


def test_split_hours_and_titles():
    a = datetime(2026, 10, 11, 14, 23).astimezone()
    ep = {"id": "now:r2:1", "title": "t", "title_prefix": "R2 otse", "start": a.isoformat(),
          "end": (a + timedelta(minutes=120)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
          "lineup": [{"start": a.isoformat(), "end": (a + timedelta(hours=3)).isoformat(), "name": "Saade"}]}
    parts = k.split_hours(ep)
    assert len(parts) == 3 and parts[0]["title"].startswith("R2 otse: Saade")


def test_timer_same_start_end_skipped():
    t = {"id": "timer:x", "station": "r", "name": "n", "days": list(range(7)), "start": "07:00", "end": "07:00"}
    assert k.expand_timers([t], datetime.now(timezone.utc)) == []


def test_prune_done():
    now = datetime.now(timezone.utc)
    keys = {"a@" + (now - timedelta(days=5)).isoformat(), "b@" + now.isoformat(), "junk"}
    assert {x.split("@")[0] for x in k.prune_done(keys)} == {"b"}


def test_normalize_config_drops_bad_timers():
    cfg = w.normalize_config({"timers": [{"id": "timer:a", "start": "25:00", "end": "08:00"},
                                         {"id": "timer:b", "station": "r", "days": [0, 9], "start": "07:00", "end": "08:00"}]})
    assert [t["id"] for t in cfg["timers"]] == ["timer:b"] and cfg["timers"][0]["days"] == [0]


def test_fetch_sky_weekly_template():
    data = {"data": [
        {"name": "Hommik", "days": [1, 2, 3, 4, 5], "start_time": "06:00", "end_time": "10:00",
         "show": {"title": "Sky Plus Hommik", "slug": "sky-plus-hommik"}, "cover_image_url": "x.webp"},
        {"name": "Öö", "days": [6], "start_time": "22:00", "end_time": "00:00", "show": None},
    ]}
    orig, k.http_json = k.http_json, lambda url: data
    try:
        now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)  # esmaspäev
        eps = k.fetch_sky({"id": "skyplus", "schedule": {"type": "sky", "channel": "1"}}, now)
    finally:
        k.http_json = orig
    morning = [e for e in eps if e["show"]["id"] == "skyplus:sky-plus-hommik"]
    assert len({e["id"] for e in eps}) == len(eps)
    assert all(k.parse_ts(e["start"]).astimezone().weekday() < 5 for e in morning)
    night = next(e for e in eps if e["show"]["id"] == "skyplus:oo")
    assert k.parse_ts(night["end"]) - k.parse_ts(night["start"]) == timedelta(hours=2)
    assert night["show"]["name"] == "Öö" and morning[0]["show"]["thumbnail"] == "x.webp"


def test_err_planned_weekly_from_old_import():
    # kava toodud kuu aega tagasi: Vikerhommik E–R 05:30–09:00 (Tallinna aeg)
    tz = k.tallinn_tz()
    base = datetime(2026, 9, 14, 5, 30, tzinfo=tz)  # esmaspäev
    eps = [{"id": f"vikerraadio:{i}", "station": "vikerraadio", "start": (base + timedelta(days=i)).isoformat(),
            "end": (base + timedelta(days=i, hours=3, minutes=30)).isoformat(), "rerun": False,
            "show": {"id": "vikerraadio:953", "name": "Vikerhommik", "thumbnail": None}} for i in range(5)]
    eps.append({"id": "vikerraadio:99", "station": "vikerraadio", "start": (base + timedelta(days=8)).isoformat(),
                "end": (base + timedelta(days=8, hours=1)).isoformat(), "rerun": True,
                "show": {"id": "vikerraadio:1", "name": "Kordus", "thumbnail": None}})
    stations = {"vikerraadio": {"id": "vikerraadio", "schedule": {"type": "err", "channel": "vikerraadio"}}}
    shows = [{"id": "vikerraadio:953", "name": "Vikerhommik", "station": "vikerraadio"},
             {"id": "vikerraadio:1", "name": "Kordus", "station": "vikerraadio"}]  # ainult kordused, reruns=False
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)  # kolmapäev
    out = k.err_planned({"episodes": eps}, shows, stations, now)
    days = sorted({e["id"].split("@")[1][:10] for e in out})
    assert days == ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]  # T, K, N, R (eile..+2)
    assert all(k.parse_ts(e["start"]).astimezone(tz).strftime("%H:%M") == "05:30" for e in out)
    assert all(e["show"]["id"] == "vikerraadio:953" for e in out)
    assert k.err_planned({"episodes": eps}, [], stations, now) == []  # tellimuseta ei salvesta


def test_parse_aripaev_next_payload():
    import json
    items = [{"start": "2026-10-22T06:45:00+03:00", "end": "2026-10-22T10:00:00+03:00", "series": "Hommikuprogramm",
              "seriesSlug": "hommikuprogramm", "title": "Tesla tulemused ", "host": "Lauri Leet", "description": "$73"},
             {"start": "2026-10-22T18:00:00+03:00", "end": "2026-10-22T19:00:00+03:00", "series": "Juhi jutud",
              "seriesSlug": "juhi-jutud", "title": "Halb juht *", "host": "Rivo Sarapik"},
             {"start": "2026-10-22T20:00:00+03:00", "end": "2026-10-23T06:45:00+03:00", "series": "Muusika"}]
    payload = '1:["$","div",null,{"days":' + json.dumps(items, ensure_ascii=False, separators=(",", ":")) + '}]'
    html = '<script>self.__next_f.push([1,%s])</script>' % json.dumps(payload, ensure_ascii=False)
    eps = k.parse_aripaev(html, {"id": "aripaev"})
    assert [e["show"]["id"] for e in eps] == ["aripaev:hommikuprogramm", "aripaev:juhi-jutud", "aripaev:muusika"]
    assert eps[0]["title"] == "Tesla tulemused" and eps[0]["description"] == "Saatejuht Lauri Leet" and not eps[0]["rerun"]
    assert eps[1]["rerun"] and eps[1]["title"] == "Halb juht"
    assert eps[2]["title"] == "Muusika 22.10.2026" and eps[0]["id"] == "aripaev:hommikuprogramm@2026-10-22T0645"


def test_update_only_when_newer():
    assert k.is_newer("b", "2026-10-12T20:00:00+03:00", "a", "2026-10-12T19:00:00+03:00")
    assert not k.is_newer("b", "2026-10-12T17:50:56+03:00", "a", "2026-10-12T20:10:00+03:00")  # leht veel vana
    assert k.is_newer("b", "2026-10-12T17:50:56+03:00", "a", None)  # vana paigaldus (aeg teadmata)
    assert not k.is_newer("a", "x", "a", None)


def test_load_env_env_vars_and_file():
    """Testib keskkonnamuutujate ja seadistusfaili laadimist ning salvestuskausta."""
    import os
    import tempfile
    from storage import make_storage
    orig_env = dict(os.environ)
    try:
        os.environ["STORAGE"] = "local"
        os.environ["LOCAL_DIR"] = "/tmp/test_raadio_dir"
        os.environ["PUBLIC_URL"] = "https://raadio.example.com"
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write("LOCAL_DIR=/tmp/from_file\nWEB_USER=testuser\n")
            f_path = Path(f.name)
        loaded = k.load_env(f_path)
        assert loaded["STORAGE"] == "local"
        assert loaded["LOCAL_DIR"] == "/tmp/from_file"  # fail kirjutab üle
        assert loaded["WEB_USER"] == "testuser"
        assert loaded["PUBLIC_URL"] == "https://raadio.example.com"
        st = make_storage(loaded)
        assert st.root == Path("/tmp/from_file").resolve()
        f_path.unlink()
    finally:
        os.environ.clear()
        os.environ.update(orig_env)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
