#!/usr/bin/env python3
"""Raadiosalvestaja juhtkäsk (Mac ja Windows).

    raadio            olek: kas töötab, mida salvestab, veebilehe aadress, viimased logiread
    raadio start|stop|restart
    raadio log        logi reaalajas (Ctrl+C väljub)
    raadio url        veebilehe aadress
    raadio test [sekundid] [jaam]   testsalvestus
    raadio update     uuenda uusimale versioonile (seaded ja salvestused jäävad alles)
"""

import os
import plistlib
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kuku_recorder as rec  # noqa: E402
from storage import make_storage  # noqa: E402

MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"
MAC_LABELS = ["ee.raadiosalvestaja", "ee.kuku.salvestaja"]  # uus, vana
WIN_TASK = "Raadiosalvestaja"
NO_WINDOW = {"creationflags": 0x08000000} if WIN else {}


def sh(cmd, check=False):
    return subprocess.run(cmd, capture_output=True, text=True, check=check, **NO_WINDOW)


def ps(script):
    return sh(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])


# --- teenus -------------------------------------------------------------------
def mac_label():
    for label in MAC_LABELS:
        if (Path.home() / "Library/LaunchAgents" / f"{label}.plist").exists():
            return label
    return MAC_LABELS[0]


def mac_plist():
    return Path.home() / "Library/LaunchAgents" / f"{mac_label()}.plist"


def running():
    if MAC:
        return sh(["launchctl", "print", f"gui/{os.getuid()}/{mac_label()}"]).returncode == 0
    if WIN:
        return ps(f"(Get-ScheduledTask -TaskName '{WIN_TASK}' -ErrorAction SilentlyContinue).State").stdout.strip() == "Running"
    return False


def kill_windows_ffmpeg():
    # Windowsis ei sure lapsprotsessid koos vanemaga
    ps("Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe'\" | "
       "Where-Object { $_.CommandLine -like '*write_xing*' } | Invoke-CimMethod -MethodName Terminate | Out-Null")


def show_access():
    """Veebilehe aadress (+ kasutajanimi), kui arvuti ise lehte jagab."""
    u = url()
    if not u:
        return
    print(f"  🌐 {u}")
    e = env()
    if e.get("WEB_PASS"):
        print(f"  Kasutajanimi: {e.get('WEB_USER') or 'raadio'}")


def start():
    if running():
        print("juba töötab")
        return show_access()
    if MAC:
        sh(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(mac_plist())])
    elif WIN:
        ps(f"Start-ScheduledTask -TaskName '{WIN_TASK}'")
    time.sleep(2)
    if running():
        print("käivitatud")
        show_access()
    else:
        print("käivitamine ebaõnnestus – vaata: raadio log")


def stop(ask=True):
    st = read_status()
    if ask and st and st.get("recording") and sys.stdin.isatty():
        if input("Praegu käib salvestus – see katkeb. Peatada ikkagi? [j/E] ").strip().lower() != "j":
            return
    if not running():
        return print("juba peatatud")
    if MAC:
        sh(["launchctl", "bootout", f"gui/{os.getuid()}/{mac_label()}"])
    elif WIN:
        ps(f"Stop-ScheduledTask -TaskName '{WIN_TASK}'")
        kill_windows_ffmpeg()
    print("peatatud (käivitub uuesti 'raadio start' või arvuti taaskäivitusega)")


def restart():
    if MAC and running():
        sh(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{mac_label()}"])
    else:
        stop(ask=False)
        start()
        return
    print("taaskäivitatud")
    show_access()


# --- olek ---------------------------------------------------------------------
def env():
    return rec.load_env(rec.CRED_FILE)


def log_file():
    e = env()
    if e.get("LOG_FILE"):
        return Path(e["LOG_FILE"]).expanduser()
    if MAC and mac_plist().exists():
        return Path(plistlib.loads(mac_plist().read_bytes()).get("StandardOutPath", ""))
    return Path.home() / "Library/Logs/raadiosalvestaja.log"


def read_status():
    try:
        return make_storage(env()).get_json("status.json", None)
    except Exception:
        return None


def url():
    e = env()
    st = make_storage(e)
    if st.kind != "local" and e.get("WEB") != "1":
        return None
    return f"http://{rec.lan_address()}:{e.get('WEB_PORT') or 8788}"


def fmt_time(iso):
    return datetime.fromisoformat(iso).astimezone().strftime("%d.%m %H:%M")


def status():
    on = running()
    print("● töötab" if on else "○ peatatud")
    st = read_status()
    if st:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(st["updated"])).total_seconds() / 60
        if on and age > 3:
            print(f"  ⚠ salvestaja pole {round(age)} min ühendust võtnud")
        for r in st.get("recording") or []:
            print(f"  ⏺ salvestab: {r['title']} ({round((r.get('bytes') or 0) / 1048576)} MB)")
        for n in (st.get("next") or [])[:3]:
            print(f"  ⏭ {fmt_time(n['start'])}  {n['title']}")
        if st.get("last_error"):
            print(f"  ⚠ {st['last_error']}")
        up = st.get("update")
        if up:
            print(f"  ⬆ uuendus saadaval: {st.get('version')} → {up['latest']}" + (f" – {up['notes']}" if up.get("notes") else ""))
            print("    uuenda: raadio update")
    show_access()
    lf = log_file()
    if lf.exists():
        print("\nViimased logiread:")
        print("".join(lf.read_text(encoding="utf-8", errors="replace").splitlines(True)[-5:]), end="")


def follow_log(n=30):
    lf = log_file()
    if not lf.exists():
        return print(f"logi pole veel: {lf}")
    with open(lf, encoding="utf-8", errors="replace") as f:
        print("".join(f.readlines()[-n:]), end="")
        try:
            while True:
                line = f.readline()
                if line:
                    print(line, end="", flush=True)
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass


def update():
    """Laeb uusima versiooni (sama paigaldaja mis esmasel paigaldusel, ilma küsimusteta)."""
    if (rec.APP_ROOT / ".git").exists() or not rec.local_version():
        return print("See on arenduskoopia (git) – uuenda käsuga: git pull. Automaatne uuendus on paigaldatud koopiale.")
    st = read_status()
    if st and st.get("recording") and sys.stdin.isatty():
        names = ", ".join(r["title"] for r in st["recording"])
        if input(f"Praegu salvestatakse ({names}) – uuendus katkestab selle. Jätkata? [j/E] ").strip().lower() != "j":
            return
    print(f"Praegune versioon: {rec.local_version()}")
    env_ = dict(os.environ, RAADIO_NONINTERACTIVE="1", RAADIO_DIR=str(rec.APP_ROOT))
    if MAC:
        os.execvpe("zsh", ["zsh", "-c", "curl -fsSL https://raadio.mastering.ee/install | zsh"], env_)
    elif WIN:
        # eraldi aknas ja viivitusega: see protsess (venv-i python) peab enne lõppema, muidu on failid lukus
        cmd = ("Start-Sleep 2; $env:RAADIO_NONINTERACTIVE='1'; "
               "irm https://raadio.mastering.ee/install.ps1 | iex; Read-Host 'Valmis – vajuta Enter'")
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                         creationflags=0x00000010, env=env_)  # CREATE_NEW_CONSOLE
        print("Uuendus käivitus eraldi aknas.")
    else:
        print("Toetatud on macOS ja Windows.")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd in ("status", "olek"):
        status()
    elif cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        restart()
    elif cmd == "log":
        follow_log(int(argv[2]) if len(argv) > 2 else 30)
    elif cmd == "url":
        print(url() or "veebileht on Cloudflare Pages'is (R2 režiim)")
    elif cmd == "update":
        update()
    elif cmd == "test":
        subprocess.run([sys.executable, str(HERE / "kuku_recorder.py"), "--test", *argv[2:]])
    else:
        print(__doc__)


if __name__ == "__main__":
    if WIN:
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv)
