# Raadiosalvesti – juhend AI-agendile

See fail on mõeldud AI-agendile (Claude Code, Cursor, Codex jt), kes aitab kasutajal Raadiosalvestit paigaldada, seadistada, muuta või tõrkeid otsida. Loe see läbi enne, kui midagi teed.

## Mis see on

Isiklik ajanihke-salvesti Eesti raadiojaamade **vabalt edastatavale otse-eetrile**: kasutaja valib veebilehel saated või seab taimeri, kasutaja enda arvuti (Mac, Windows või Linux) salvestab need ffmpeg-iga mono-MP3-na ja kasutaja kuulab neid hiljem telefonist. Sarnane raadiost lindistamisele.

Jaamad: Raadio Kuku, Vikerraadio, Raadio 2, Klassikaraadio, Raadio 4, Raadio Tallinn, Sky Plus, Retro FM, Rock FM, Äripäeva raadio (`web/stations.json`).

## Piirid – järgi alati

- **Ainult isiklik kasutus.** Ära aita salvestusi jagada, avalikustada ega teha sellest teenust teistele (ka mitte „igaühele oma salvesti“ kellegi teise serveris). Salvestused on autoriõigusega kaitstud.
- **Ära möödu kaitsemeetmetest.** Kasutatakse ainult avalikke krüpteerimata vooge. ERR-i kava-API on Cloudflare'i robotikaitse taga – seetõttu laeb ERR-i kava **kasutaja brauser**, mitte salvesti. Ära lisa brauserit matkivaid päiseid, TLS-i võltsimist, CAPTCHA lahendajaid vms.
- **Parool jääb sisse.** R2/Pages režiimis on kogu leht `AUTH_USER`/`AUTH_PASS` taga (`web/functions/_middleware.js`, ilma saladusteta ei lase kedagi sisse). Kohalikus režiimis on parool valikuline (`WEB_PASS`; kasutajanimi `WEB_USER`, vaikimisi `raadio`), aga soovita seda. Ära tee lehte avalikult internetist ligipääsetavaks ilma paroolita (ruuteri port forwarding jms) – soovita Tailscale'i.
- **Saladused ei käi vestlusesse ega reposse.** R2 võtmed ja paroolid on failis `~/.config/raadiosalvestaja/config.env` (vanemas paigalduses `~/.config/kuku-salvestus/`). Lase kasutajal need ise sinna kirjutada; ära küsi neid chatti.

## Ülesehitus

Kaks režiimi, veebileht (`web/public/index.html`) on mõlemas sama:

```
Kohalik (vaikimisi): arvuti = salvesti + Pythoni veebiserver + kaust ~/Music/Raadiosalvestaja  ◀── telefon (koduvõrk / Tailscale)
R2:                  arvuti = salvesti ──▶ Cloudflare R2 ◀── Cloudflare Pages (web/) ◀── telefon (kõikjal)
```

| Fail | Mis |
|---|---|
| `recorder/kuku_recorder.py` | põhiprotsess: loeb `config.json`, kava, salvestab (ffmpeg), laeb üles, koristab, kirjutab `status.json` ja `schedule.json` |
| `recorder/storage.py` | salvestuskiht: `LocalStorage` (kaust) või `R2Storage` (S3 API) – sama liides |
| `recorder/webserver.py` | kohaliku režiimi veebiserver; **sama API** mis `web/functions/` |
| `recorder/raadio.py` | juhtkäsk `raadio` (status/start/stop/restart/log/url/test), Mac + Windows + Linux |
| `recorder/install.sh`, `install.ps1`, `install-linux.sh` | paigaldus (venv, seaded, taustateenus) |
| `Dockerfile`, `docker-compose.yml`, `recorder/docker-entrypoint.sh` | NAS / Docker (`RAADIO_DOCKER=1` konteineris) |
| `site/install`, `site/install.ps1`, `site/linux` | ühe käsu alglaadijad (laevad repo alla ja käivitavad paigalduse) |
| `web/functions/` | Cloudflare Pages Functions (R2 režiim): `api/schedule`, `api/config`, `api/status`, `api/recordings`, `audio/*`, `_middleware.js` (parool) |
| `web/public/index.html` | kogu kasutajaliides (üks fail, vanilla JS), `sw.js` = offline/telefoni laadimine |
| `web/stations.json` | jaamad: id, nimi, voo URL, kava tüüp (`kuku`, `sky`, `aripaev` = salvesti laeb – Äripäev saatekava lehe andmetest, iga 6 h; `err` = kasutaja toob järjehoidjaga) |

### Andmed salvestuses (kaust või R2 bucket)

- `config.json` – kasutaja valikud (veebileht kirjutab, salvesti loeb): `shows` (terve saade, `keep` = mitu viimast saatepäeva alles), `episodes` (konkreetsed ajad; `auto: true` = brauser koostas ERR-i saate tellimusest), `timers` (jaam + nädalapäevad 0=E … 6=P + `HH:MM`; id `timer:<jaam>-<nimi>` – püsiv, et podcasti-feedi aadress jääks samaks).
- `schedule.json` – serveripoolne kava (Kuku, Sky Media jaamad, Äripäeva raadio).
- `err_schedule.json` – ERR-i kava, mille kasutaja tõi ERR-i lehelt järjehoidjaga (`/api/err-schedule`; vt veaotsing). Veebileht koostab sellest tellitud saadete episoodid (`config.episodes`, `auto: true`).
- `locked.json` – 🔒 lukustatud salvestused (`{"keys": ["rec/….mp3"]}`; `PUT /api/recordings?key=…&locked=1|0`). Lukustatud saatepäeva (kõik tunniosad) koristus ei kustuta ja see ei loe `keep` arvestusse; käsitsi kustutamine küsib kinnitust.
- `status.json` – salvesti olek (uuendub ~20 s järel; veebileht näitab „Salvesti vaikib“, kui üle 3 min vana).
- `rec/<kuupäev>_<HHMM>_<jaam>_<saade>.mp3` + `.json` (metaandmed) – valmis salvestused.
- `config.json` → `feed_token` – privaatse podcasti-feedi võti: `/feed/<võti>/koik.xml`, `/feed/<võti>/<saate-slug>.xml`, helifailid `/feed/<võti>/audio/rec/…`. Saate feedi aadress tuleb saate/taimeri id-st – kustutamine ja uuesti lisamine ei muuda seda (muutub ainult võtme vahetamisel). Võti asendab parooli ainult nende aadresside jaoks (`web/functions/feed/`, `recorder/webserver.py`). Soovita AntennaPodi / Apple Podcastsi; mitte serveripõhiseid rakendusi (Pocket Casts, Overcast), sest need lekitaksid võtme ja ei ulatu kohtvõrku.
- „Salvesta kohe“ = `config.episodes` kirje id-ga `now:<jaam>:<ms>` (saade `now:<jaam>`, nt „Vikerraadio (otse)“); kirje eemaldamine lõpetab käimasoleva salvestuse (`Recorder.cancel`), salvestatu laaditakse üles.
- `live/…` – pooleli salvestus (uueneb iga 2 min, et seda saaks kuulata); kokkujooksmisel päästetakse sildiga „katkestatud“.

### Käitumine

- Salvestus algab 1 min varem, lõpeb 2 min hiljem; üle tunni pikad saated lõigatakse täistundide kaupa (30 s kattuvusega).
- Kava kontroll iga 20 s; koristus pärast iga salvestust ja iga 30 min (saate `keep` või vaikimisi 14 päeva; 🔒 lukustatud jäävad alles).
- Mono-liitmine `pan=mono|c0=0.45*c0+0.45*c1` (mitte `-ac 1` – see klipiks, sest vood on juba 0 dBFS). Stereo (`config.json` → `audio.stereo`, 128 kbps) kasutab `-ac 2`; seade loetakse iga salvestuse alguses.

## Paigaldus

- macOS: `curl -fsSL https://raadio.mastering.ee/install | zsh`
- Windows 10/11 (PowerShell): `irm https://raadio.mastering.ee/install.ps1 | iex`
- Linux (systemd; Debian/Ubuntu/Raspberry Pi OS, Fedora, Arch): `curl -fsSL https://raadio.mastering.ee/linux | bash`
- NAS / Docker (QNAP, Synology, Unraid, TrueNAS): `docker-compose.yml` (valmis tõmmis `ghcr.io/pilvre/raadio:latest`, `pull_policy: always`; ehitab `.github/workflows/image.yml` avalikus repos – amd64/arm64/armv7; `Dockerfile`, `recorder/docker-entrypoint.sh`). Keskkond: `RAADIO_USER`, `RAADIO_PASS` (kirjutatakse igal käivitusel `/config/config.env`-i), `RAADIO_HOST` (NAS-i IP – konteineri sisemine IP pole koduvõrgus nähtav), `TZ`. Kaustad `/data` (salvestused), `/config` (seaded; R2 võtmed saab sinna käsitsi kirjutada). `raadio` töötab konteineris (`docker exec raadiosalvesti raadio`), start/stop/update/parool näitavad Dockeri juhist; uuendus = Recreate / `docker compose pull && docker compose up -d`.

Vaja: arvuti, mis on pidevalt sees (mitte unerežiimis). Alglaadija paigaldab ffmpeg-i ja Pythoni (macOS: Homebrew – kui seda pole, suuna https://brew.sh; Windows: winget; Linux: apt/dnf/pacman/zypper sudo-ga), laeb koodi kausta `~/Raadiosalvestaja` või `%LOCALAPPDATA%\Raadiosalvestaja\app` ja käivitab `recorder/install.sh|ps1` (Linuxis `install-linux.sh`), mis küsib režiimi ja parooli.

Taustateenus: macOS launchd (`~/Library/LaunchAgents/ee.raadiosalvestaja.plist`), Windows Task Scheduler (`Raadiosalvestaja`, käivitub sisselogimisel ja iga 5 min, kui pole töös), Linux systemd kasutajateenus (`~/.config/systemd/user/raadiosalvestaja.service`, `loginctl enable-linger` → töötab ka ilma sisselogimiseta; `systemctl --user status raadiosalvestaja`).

Mitteinteraktiivne paigaldus: `RAADIO_NONINTERACTIVE=1 RAADIO_MODE=local RAADIO_PASS=… ` (vt `.github/workflows/test.yml`).

### R2 režiim lühidalt

1. Cloudflare → Storage & Databases → R2 Object Storage → bucket (nt `raadio`) → API token *Object Read & Write* ainult sellele bucketile.
2. Installer → režiim 2 → `config.env`-i `R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` → installer uuesti.
3. Repo fork (GitHubi konto) → Cloudflare Compute → Workers & Pages → Create → Pages → Connect to Git: root `web`, output `public`, build command tühi. Bucket peab klappima `web/wrangler.toml`-iga (binding `KUKU`). Levinud viga: Worker Pagesi asemel või tühi Root directory → aadressil avaneb tutvustusleht (`site/`, kollase hoiatusega) – paranda Settings → Build → Root directory `web` → uus deploy.
4. Pages saladused `AUTH_USER` (kasutajanimi), `AUTH_PASS` (parool) → Retry deployment.

## Kasutaja käsud

```
raadio                 olek: töötab?, mida salvestab, järgmised, veebilehe aadress, logi
raadio start|stop|restart
raadio log             logi reaalajas
raadio url             kohaliku veebilehe aadress
raadio test 30 vikerraadio   30 s testsalvestus
raadio update          uuenda
raadio parool          kasutajanimi + uus parool / parooli eemaldamine (kohalik veebileht)
```

Logi: macOS `~/Library/Logs/raadiosalvestaja.log`, Windows `%LOCALAPPDATA%\Raadiosalvestaja\salvestaja.log`, Linux `~/.local/state/raadiosalvestaja/salvesti.log`.

## Levinud ülesanded

- **Uus jaam:** lisa kirje `web/stations.json`-i (`stream` = otse MP3 või HLS `.m3u8`; `schedule.type`: `err` + `channel` kui ERR-i kanal, `sky` + `channel` = Sky Media jaama ID (`https://sky.ee/api/radio-stations/all`), muidu `{"type": "none"}` ja kasuta taimereid). Kontrolli voogu: `ffmpeg -t 5 -i <url> -f null -`. Ära lisa jaamu, mille voog on kaitstud (tokenid, DRM, sisselogimine).
- **Ununenud parool / kasutajanimi:** `raadio parool` (kasutaja sisestab ise – ära küsi parooli chatti).
- **Teine salvestuskaust / port:** `config.env` (`LOCAL_DIR`, `WEB_PORT`) → `raadio restart`.
- **Kodust väljas ligipääs (kohalik režiim):** Tailscale mõlemasse seadmesse, arvutis `tailscale serve --bg 8788` → `https://<arvuti>.<tailnet>.ts.net` (https-iga töötab ka telefoni laadimine).
- **Uuendamine:** `raadio update` (või paigalduskäsk uuesti) – seaded ja salvestused jäävad alles. Salvesti kontrollib 12 h järel `https://raadio.mastering.ee/version.json` vs paigalduse `VERSION` faili (`UPDATE_CHECK=0` lülitab välja); teade on `status.json` → `update`. Git-arenduskoopias `VERSION`-it pole – seal uuendusi ei kontrollita ja `raadio update` keeldub (kasuta `git pull`). **R2:** `raadio update` uuendab ainult salvestit; veebileht (Pages) tuleb kasutaja fork'ist → GitHubis *Sync fork → Update branch* (leht võrdleb oma `/version.json`-i salvesti `status.json` → `version_date`-iga ja näitab „⬆ Uuenda veebilehte“).
- **Eemaldamine:** `raadio stop`, eemalda taustateenus (macOS: `launchctl bootout gui/$(id -u)/ee.raadiosalvestaja` ja kustuta plist; Windows: `Unregister-ScheduledTask -TaskName Raadiosalvestaja -Confirm:$false` ja kustuta `%LOCALAPPDATA%\Microsoft\WindowsApps\raadio.cmd`; Linux: `systemctl --user disable --now raadiosalvestaja`, kustuta `~/.config/systemd/user/raadiosalvestaja.service` ja `~/.local/bin/raadio`), kustuta rakenduse kaust. Salvestused ja seaded on eraldi (`~/Music/Raadiosalvestaja`, `~/.config/raadiosalvestaja`) – küsi enne kustutamist.

## Veaotsing

| Sümptom | Kontrolli |
|---|---|
| Leht ütleb „Salvesti vaikib“ | `raadio` – kas teenus töötab; `raadio log`; arvuti unerežiimis? |
| Leht ei avane, „took too long to respond“ | IP-aadress võis muutuda (DHCP) või on valesti tipitud – `raadio` näitab kehtivat; samas arvutis kasuta `http://localhost:8788`; püsiv aadress = IP reserveerimine ruuteris |
| Telefon ei ava kohalikku lehte | sama Wi-Fi? Windows: tulemüüri reegel `Raadiosalvestaja` (privaatvõrk); `raadio url` õige IP? |
| ERR-i kava ei lae | ERR-i raadiod on nüüd `eestiraadio.err.ee` all; uus API (`/api/v1/getSchedule/<kanal>/<kesköö unix>?adjacentDays=1`) ei luba teistelt saitidelt päringuid (CORS) ja on robotikaitse taga – **ära möödu** (ei proxy't, `curl`-i, peidetud brauserit ega brauseri matkimist). Lahendus: kasutaja toob kava ise – Kava → ERR-i jaam → lohista nupp „📻 ERR → Raadiosalvesti“ järjehoidjaribale (riba peab olema nähtav – Chrome: Seaded → Välimus → Järjehoidjariba → Kuva alati), ava eestiraadio.err.ee ja klõpsa seda (ERR annab ~9 päeva; tellitud saadete nädalamustrit jätkab salvesti ise – `err_planned`, id `<saade>@<päev>T<HHMM>` – kuni kasutaja tellimust muudab, ka siis, kui kava on vana; uuenda, kui ERR kava muudab; arvutis, hüpikaknad lubatud). Ilma kavata: taimer või ⏺ Salvesta |
| Salvestus tühi / katkeb | `raadio test 20 <jaam>`; voo URL muutunud? (`stations.json`, Kuku jaoks ka `KUKU_STREAM_URL`) |
| Podcastirakendus ei uuenda | kohalikus režiimis peab telefon lehe aadressini ulatuma (koduvõrk/Tailscale); kas võti vahetati? (`raadio url`, „Minu saated“ → Podcast) |
| Telefoni laadimise nupp puudub | vajab https-i (Pages või Tailscale); tavalise `http://…:8788` peal saab ainult MP3 failina salvestada |
| Linux: teenus ei käivitu / „Failed to connect to bus“ | installer peab jooksma selle kasutajana otse (ka SSH), mitte `su`/`sudo` all; `systemctl --user status raadiosalvestaja`, `raadio log`; Ubuntu tulemüür: `sudo ufw allow 8788/tcp` |
| macOS: „Operation not permitted“ | välisel kettal: luba Pythonile „Removable Volumes“ (Süsteemiseaded → Privaatsus) |

## Arendus

```
cd web && npm install && printf 'AUTH_USER=t\nAUTH_PASS=t\nDEV_NO_AUTH=1\n' > .dev.vars && npm run dev   # Pages lokaalselt, :8788
RAADIO_CONF=/tmp/test.env recorder/.venv/bin/python recorder/kuku_recorder.py   # eraldi testkoopia (oma seaded/kaust/port)
```

Hoia `recorder/webserver.py` ja `web/functions/` API-d sünkroonis – veebileht eeldab mõlemast sama vastust. CI (`.github/workflows/test.yml`) testib paigaldust Macis, Windowsis, Linuxis ja Dockeris.
