# Raadiosalvestaja – juhend AI-agendile

See fail on mõeldud AI-agendile (Claude Code, Cursor, Codex jt), kes aitab kasutajal Raadiosalvestajat paigaldada, seadistada, muuta või tõrkeid otsida. Loe see läbi enne, kui midagi teed.

## Mis see on

Isiklik ajanihke-salvestaja Eesti raadiojaamade **vabalt edastatavale otse-eetrile**: kasutaja valib veebilehel saated või seab taimeri, kasutaja enda arvuti (Mac või Windows) salvestab need ffmpeg-iga mono-MP3-na ja kasutaja kuulab neid hiljem telefonist. Sarnane raadiost lindistamisele.

Jaamad: Raadio Kuku, Vikerraadio, Raadio 2, Klassikaraadio, Raadio 4, Raadio Tallinn (`web/stations.json`).

## Piirid – järgi alati

- **Ainult isiklik kasutus.** Ära aita salvestusi jagada, avalikustada ega teha sellest teenust teistele (ka mitte „igaühele oma salvestaja“ kellegi teise serveris). Salvestused on autoriõigusega kaitstud.
- **Ära möödu kaitsemeetmetest.** Kasutatakse ainult avalikke krüpteerimata vooge. ERR-i kava-API on Cloudflare'i robotikaitse taga – seetõttu laeb ERR-i kava **kasutaja brauser**, mitte salvestaja. Ära lisa brauserit matkivaid päiseid, TLS-i võltsimist, CAPTCHA lahendajaid vms.
- **Parool jääb sisse.** R2/Pages režiimis on kogu leht `AUTH_USER`/`AUTH_PASS` taga (`web/functions/_middleware.js`, ilma saladusteta ei lase kedagi sisse). Kohalikus režiimis on parool valikuline (`WEB_PASS`; kasutajanimi `WEB_USER`, vaikimisi `raadio`), aga soovita seda. Ära tee lehte avalikult internetist ligipääsetavaks ilma paroolita (ruuteri port forwarding jms) – soovita Tailscale'i.
- **Saladused ei käi vestlusesse ega reposse.** R2 võtmed ja paroolid on failis `~/.config/raadiosalvestaja/config.env` (vanemas paigalduses `~/.config/kuku-salvestus/`). Lase kasutajal need ise sinna kirjutada; ära küsi neid chatti.

## Ülesehitus

Kaks režiimi, veebileht (`web/public/index.html`) on mõlemas sama:

```
Kohalik (vaikimisi): arvuti = salvestaja + Pythoni veebiserver + kaust ~/Music/Raadiosalvestaja  ◀── telefon (koduvõrk / Tailscale)
R2:                  arvuti = salvestaja ──▶ Cloudflare R2 ◀── Cloudflare Pages (web/) ◀── telefon (kõikjal)
```

| Fail | Mis |
|---|---|
| `recorder/kuku_recorder.py` | põhiprotsess: loeb `config.json`, kava, salvestab (ffmpeg), laeb üles, koristab, kirjutab `status.json` ja `schedule.json` |
| `recorder/storage.py` | salvestuskiht: `LocalStorage` (kaust) või `R2Storage` (S3 API) – sama liides |
| `recorder/webserver.py` | kohaliku režiimi veebiserver; **sama API** mis `web/functions/` |
| `recorder/raadio.py` | juhtkäsk `raadio` (status/start/stop/restart/log/url/test), Mac + Windows |
| `recorder/install.sh`, `install.ps1` | paigaldus (venv, seaded, taustateenus) |
| `site/install`, `site/install.ps1` | ühe käsu alglaadijad (laevad repo alla ja käivitavad paigalduse) |
| `web/functions/` | Cloudflare Pages Functions (R2 režiim): `api/schedule`, `api/config`, `api/status`, `api/recordings`, `audio/*`, `_middleware.js` (parool) |
| `web/public/index.html` | kogu kasutajaliides (üks fail, vanilla JS), `sw.js` = offline/telefoni laadimine |
| `web/stations.json` | jaamad: id, nimi, voo URL, kava tüüp (`kuku` = serveri pool, `err` = brauseris) |

### Andmed salvestuses (kaust või R2 bucket)

- `config.json` – kasutaja valikud (veebileht kirjutab, salvestaja loeb): `shows` (terve saade, `keep` = mitu viimast saatepäeva alles), `episodes` (konkreetsed ajad; `auto: true` = brauser koostas ERR-i saate tellimusest), `timers` (jaam + nädalapäevad 0=E … 6=P + `HH:MM`).
- `schedule.json` – serveripoolne kava (praegu Kuku).
- `status.json` – salvestaja olek (uuendub ~20 s järel; veebileht näitab „Salvestaja vaikib“, kui üle 3 min vana).
- `rec/<kuupäev>_<HHMM>_<jaam>_<saade>.mp3` + `.json` (metaandmed) – valmis salvestused.
- `live/…` – pooleli salvestus (uueneb iga 2 min, et seda saaks kuulata); kokkujooksmisel päästetakse sildiga „katkestatud“.

### Käitumine

- Salvestus algab 1 min varem, lõpeb 2 min hiljem; üle tunni pikad saated lõigatakse täistundide kaupa (30 s kattuvusega).
- Kava kontroll iga 20 s; koristus pärast iga salvestust ja iga 30 min (saate `keep` või vaikimisi 14 päeva).
- Mono-liitmine `pan=mono|c0=0.45*c0+0.45*c1` (mitte `-ac 1` – see klipiks, sest vood on juba 0 dBFS).

## Paigaldus

- macOS: `curl -fsSL https://raadio.mastering.ee/install | zsh`
- Windows 10/11 (PowerShell): `irm https://raadio.mastering.ee/install.ps1 | iex`

Vaja: arvuti, mis on pidevalt sees (mitte unerežiimis). Alglaadija paigaldab ffmpeg-i ja Pythoni (macOS: Homebrew – kui seda pole, suuna https://brew.sh; Windows: winget), laeb koodi kausta `~/Raadiosalvestaja` või `%LOCALAPPDATA%\Raadiosalvestaja\app` ja käivitab `recorder/install.sh|ps1`, mis küsib režiimi ja parooli.

Taustateenus: macOS launchd (`~/Library/LaunchAgents/ee.raadiosalvestaja.plist`), Windows Task Scheduler (`Raadiosalvestaja`, käivitub sisselogimisel ja iga 5 min, kui pole töös).

Mitteinteraktiivne paigaldus: `RAADIO_NONINTERACTIVE=1 RAADIO_MODE=local RAADIO_PASS=… ` (vt `.github/workflows/test.yml`).

### R2 režiim lühidalt

1. Cloudflare → R2 → bucket (nt `raadio`) → API token *Object Read & Write* ainult sellele bucketile.
2. Paigaldaja → režiim 2 → `config.env`-i `R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` → paigaldaja uuesti.
3. Repo fork → Cloudflare Pages → Connect to Git: root `web`, output `public`, build command tühi. Bucket peab klappima `web/wrangler.toml`-iga (binding `KUKU`).
4. Pages saladused `AUTH_USER` (kasutajanimi), `AUTH_PASS` (parool) → Retry deployment.

## Kasutaja käsud

```
raadio                 olek: töötab?, mida salvestab, järgmised, veebilehe aadress, logi
raadio start|stop|restart
raadio log             logi reaalajas
raadio url             kohaliku veebilehe aadress
raadio test 30 vikerraadio   30 s testsalvestus
```

Logi: macOS `~/Library/Logs/raadiosalvestaja.log`, Windows `%LOCALAPPDATA%\Raadiosalvestaja\salvestaja.log`.

## Levinud ülesanded

- **Uus jaam:** lisa kirje `web/stations.json`-i (`stream` = otse MP3 või HLS `.m3u8`; `schedule.type`: `err` kui ERR-i kanal, muidu jäta kava ära ja kasuta taimereid). Kontrolli voogu: `ffmpeg -t 5 -i <url> -f null -`. Ära lisa jaamu, mille voog on kaitstud (tokenid, DRM, sisselogimine).
- **Teine salvestuskaust / port / parool:** `config.env` (`LOCAL_DIR`, `WEB_PORT`, `WEB_USER`, `WEB_PASS`) → `raadio restart`.
- **Kodust väljas ligipääs (kohalik režiim):** Tailscale mõlemasse seadmesse, arvutis `tailscale serve --bg 8788` → `https://<arvuti>.<tailnet>.ts.net` (https-iga töötab ka telefoni laadimine).
- **Uuendamine:** käivita paigalduskäsk uuesti (seaded ja salvestused jäävad alles).
- **Eemaldamine:** `raadio stop`, eemalda taustateenus (macOS: `launchctl bootout gui/$(id -u)/ee.raadiosalvestaja` ja kustuta plist; Windows: `Unregister-ScheduledTask -TaskName Raadiosalvestaja -Confirm:$false` ja kustuta `%LOCALAPPDATA%\Microsoft\WindowsApps\raadio.cmd`), kustuta rakenduse kaust. Salvestused ja seaded on eraldi (`~/Music/Raadiosalvestaja`, `~/.config/raadiosalvestaja`) – küsi enne kustutamist.

## Veaotsing

| Sümptom | Kontrolli |
|---|---|
| Leht ütleb „Salvestaja vaikib“ | `raadio` – kas teenus töötab; `raadio log`; arvuti unerežiimis? |
| Telefon ei ava kohalikku lehte | sama Wi-Fi? Windows: tulemüüri reegel `Raadiosalvestaja` (privaatvõrk); `raadio url` õige IP? |
| ERR-i kava ei lae | laeb brauseris – kontrolli brauseri konsooli; serveri poolt seda ei laeta (robotikaitse) |
| Salvestus tühi / katkeb | `raadio test 20 <jaam>`; voo URL muutunud? (`stations.json`, Kuku jaoks ka `KUKU_STREAM_URL`) |
| Telefoni laadimise nupp puudub | vajab https-i (Pages või Tailscale); tavalise `http://…:8788` peal saab ainult MP3 failina salvestada |
| macOS: „Operation not permitted“ | välisel kettal: luba Pythonile „Removable Volumes“ (Süsteemiseaded → Privaatsus) |

## Arendus

```
cd web && npm install && printf 'AUTH_USER=t\nAUTH_PASS=t\nDEV_NO_AUTH=1\n' > .dev.vars && npm run dev   # Pages lokaalselt, :8788
RAADIO_CONF=/tmp/test.env recorder/.venv/bin/python recorder/kuku_recorder.py   # eraldi testkoopia (oma seaded/kaust/port)
```

Hoia `recorder/webserver.py` ja `web/functions/` API-d sünkroonis – veebileht eeldab mõlemast sama vastust. CI (`.github/workflows/test.yml`) testib paigaldust Macis ja Windowsis.
