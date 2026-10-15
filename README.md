# Raadiosalvesti

Isiklik ajanihke-salvesti Eesti raadiojaamade **vabalt kättesaadavale otse-eetrile** – nagu vanasti kassettmakk raadio kõrval. Vali kavast saated või sea taimer, sinu arvuti (Mac, Windows või Linux) salvestab need mono-MP3-na – oma kettale või soovi korral Cloudflare R2-sse – ja hiljem kuulad neid telefonist.

Jaamad: Raadio Kuku, Vikerraadio, Raadio 2, Klassikaraadio, Raadio 4, Raadio Tallinn, Sky Plus, Retro FM, Rock FM (lisa uusi failis [`web/stations.json`](web/stations.json)).

> **⚠️ Ainult isiklikuks kasutamiseks.** See ei ole ühegi raadiojaama ametlik tööriist ega seotud nendega. Salvestused on autoriõigusega kaitstud: ära jaga neid, ära tee lehte avalikuks ega ehita sellest teenust teistele. Tööriist kasutab jaamade avalike veebipleierite voo- ja kava-aadresse, mis võivad igal ajal muutuda. Kasutad omal vastutusel.

## Mida see teeb

- **Kava** järgmiseks 7 päevaks; vali terve saade (iga kord) või üksik episood, soovi korral ka kordused
- **Taimerid** mis tahes jaamale: nädalapäevad + kellaaeg (nt Vikerraadio E–R 07:00–09:00)
- **Taimeriga salvestamine** otse-eetrist, 1 min varu alguses ja 2 min lõpus; katkemisel ühendab uuesti
- **Pikad saated täistundide kaupa** (nt hommikuraadio 06–07, 07–08, …), iga tund kuulatav kohe, kui valmis
- **Pooleli salvestust saab kuulata** – uueneb iga 2 min järel
- **Säilitus saadete kaupa:** hoia alles N viimast saatepäeva (vana kustub, kui uus on valmis) või vaikimisi 14 päeva
- **Pleier:** jätkab sealt, kus pooleli jäi; 15 s / 30 s kerimine, kiirus 1–2×, lukustuskuva juhtnupud, klaviatuuri otseteed
- **Otse-eeter:** ▶ Otse kuulab valitud jaama kohe
- **Salvesta kohe:** ⏺ Salvesta paneb valitud jaama kohe salvestama 30–180 minutiks (pikem salvestus jaguneb täistundide kaupa); „Lõpeta kohe“ peatab ja salvestatu jääb alles
- **Telefoni laadimine** kuulamiseks ilma võrguta või MP3 failina
- **Heli:** mono 64 kbps (vaikimisi, jutusaated) või stereo 128 kbps (muusika) – „Minu saated“ → Salvestuse heli
- Katkenud salvestus päästetakse sildiga „katkestatud“

## Ülesehitus

Kaks režiimi – veebileht ja salvesti on mõlemas samad:

```
Kohalik (vaikimisi):  Mac: salvesti + veebiserver + kaust ~/Music/Raadiosalvestaja  ◀── telefon (koduvõrk / Tailscale)
R2:                   Mac: salvesti ──▶ Cloudflare R2 ◀── Cloudflare Pages (web/)  ◀── telefon (kõikjal)
```

- **Kohalik:** pilve pole vaja. Arvuti jagab lehte ise (Macis `http://<mac>.local:8788`, mujal `http://<arvuti-IP>:8788`). Kodust väljas ligipääsuks vt [Tailscale](#kodust-väljas-tailscale).
- **R2:** salvestused Cloudflare R2-s, leht Cloudflare Pages'is parooli taga, kuulamine kõikjal.

**Kava allikad.** Kuku kava laeb salvesti (`schedule.json`). ERR-i kava-API on robotikaitse taga, seetõttu laeb ERR-i kava veebileht sinu brauseris (nagu ERR-i enda leht) ja kirjutab valitud saated konkreetsete kellaaegadena `config.json`-i. „Salvesta kõik saated“ ERR-i jaamades uueneb seega iga kord, kui lehe avad – ava see vähemalt kord nädalas. Taimerid töötavad ilma kavata.

**Telefoni laadimine.** Salvestuse menüüst (⋯):
- **⬇ Laadi telefoni** – salvestus jääb brauserisse, leht ja pleier töötavad ka ilma võrguta (📱). Vajab **https**-i: R2/Pages režiimis alati olemas, kohalikus režiimis Tailscale'iga. iPhone'is lisa leht avaekraanile (Jaga → Lisa avaekraanile), muidu võib Safari andmed mõne nädala pärast kustutada.
- **Salvesta failina** – MP3 telefoni Failid-äppi, töötab alati.

**Autos (Android Auto, CarPlay).** „Minu saated“ → **Podcast** → lülita sisse ja lisa aadress podcastirakendusse: **AntennaPod** (Android) või **Apple Podcasts** (iPhone). Rakendus laeb salvestused telefoni, autos kuulad neid nagu podcaste. Feedi aadressis on salajane võti (`config.json` → `feed_token`), mis avab ainult salvestused; võtit saab vahetada. Ära kasuta Pocket Castsi ega Overcasti – need loevad feede oma serverite kaudu.

<details><summary><b>AntennaPod lühidalt</b> (Android, Android Auto)</summary>

1. Paigalda [AntennaPod](https://antennapod.org) (Google Play või F-Droid).
2. Raadiosalvesti lehel: **Minu saated → Podcast → Kopeeri** (kõik salvestused või üks saade).
3. AntennaPodis: **＋ (Lisa podcast) → „Lisa podcast RSS-aadressiga“** → kleebi aadress → **Telli**.
4. **Seaded → Allalaadimised:**
   - **Automaatne allalaadimine** sees, **ainult Wi-Fi-s** (soovi korral Wi-Fi filtriga ainult koduvõrk)
   - **Uuendamise intervall** nt iga tund – tunniosad jõuavad telefoni peaaegu kohe
   - **Episoodide kustutamine** „pärast kuulamist“, et telefon täis ei saaks
5. Autos: Android Auto → AntennaPod – allalaaditud salvestused mängivad ka ilma võrguta.

Kohalikus režiimis uuendab AntennaPod ainult siis, kui telefon arvuti aadressini ulatub (koduvõrk või Tailscale); mujal kuulad juba allalaaditut.
</details>

## Paigaldus

Vaja: macOS, Windows 10/11 või Linuxi (systemd; nt Ubuntu, Debian, Raspberry Pi OS, Fedora) arvuti, mis on pidevalt sees.

### Kohalik režiim (soovitatav)

**macOS** (Terminal):
```bash
curl -fsSL https://raadio.mastering.ee/install | zsh
```

**Linux** (terminal; sobib hästi ka Raspberry Pi):
```bash
curl -fsSL https://raadio.mastering.ee/linux | bash
```

**Windows 10/11** (PowerShell):
```powershell
irm https://raadio.mastering.ee/install.ps1 | iex
```

Installer paigaldab vajadusel ffmpeg-i ja Pythoni (macOS: Homebrew, Windows: winget, Linux: apt/dnf/pacman – võib küsida arvuti parooli), laeb tööriista alla ja küsib, kas hoida salvestused arvutis või Cloudflare R2-s. Käsitsi: `git clone https://github.com/pilvre/raadio.git && cd raadio/recorder && ./install.sh` (Windowsis `install.ps1`, Linuxis `install-linux.sh`).

Installer näitab lõpus kaks aadressi: samas arvutis `http://localhost:8788`, telefonis (samas Wi-Fi võrgus) nt `http://minu-mac.local:8788` või `http://<arvuti-IP>:8788`. Kehtivat aadressi näitab alati käsk `raadio`. Logi sisse kasutajanime ja parooliga, mille installerile andsid (vaikimisi kasutajanimi `raadio`; ununes? `raadio parool` näitab kasutajanime ja laseb parooli lähtestada). Salvestused on kaustas `~/Music/Raadiosalvestaja`, seaded failis `~/.config/raadiosalvestaja/config.env`.

Windowsis: luba installeril lisada tulemüüri reegel (muidu telefon lehte ei näe) ja hoia arvuti ärkvel.

Kui projekt on välisel kettal ja macOS küsib Pythonile ligipääsu („Removable Volumes“), luba see.

### Docker (Linux server)

Vt täpsemat juhendit ja pöördproksi (Traefik, Nginx, Caddy) seadistust failis [DOCKER.md](DOCKER.md).

```bash
mkdir -p data && sudo chown -R 1000:1000 data
docker compose up -d
```
Konteiner töötab turvaliselt tavakasutajana (UID 1000) ja read-only failisüsteemiga; salvestused ja seaded asuvad kaustas `./data`.

### Kodust väljas: Tailscale

[Tailscale](https://tailscale.com) (tasuta) teeb Maci telefonile kättesaadavaks ka kodust väljas – ilma ruuteri seadistamise ja avaliku aadressita:

1. Paigalda Tailscale Macile ja telefonile, logi mõlemas sama kontoga sisse
2. Macis: `tailscale serve --bg 8788`
3. Ava telefonis `https://<mac-nimi>.<tailnet>.ts.net` – https-iga töötab ka **⬇ Laadi telefoni**

### R2 režiim (Cloudflare)

Vaja lisaks: Node.js, Cloudflare konto.

1. **R2:** Cloudflare (vajadusel tee esmalt tasuta konto) → **Storage & Databases → R2 Object Storage → Create bucket** (nt `raadio`). **Manage API tokens → Create API token**: *Object Read & Write*, ainult see bucket.
2. **Salvesti:** installer → vali 2) Cloudflare R2, täida avanevas failis konto ID ja võtmed, käivita installer uuesti.
3. **Veebileht:** tee GitHubis (tasuta konto) repost koopia (fork) → Cloudflare **Compute → Workers & Pages → Create → Pages → Connect to Git** → sinu fork
   - Build command: *(tühi)*, Build output: `public`, Root directory: `web`
   - NB: vali **Pages**, mitte Worker (Cloudflare pakub vaikimisi Workerit), ja sea *Root directory (advanced)*. Kui see jääb tühjaks, näitab sinu aadress hoopis tutvustuslehte – paranda: Settings → Build → Root directory `web` → uus deploy.
   - Kui bucketi nimi pole `raadio`, muuda `web/wrangler.toml` (binding `KUKU`)
   - **Settings → Variables and Secrets** (tüüp *Secret*): `AUTH_USER` (kasutajanimi) ja `AUTH_PASS` (parool), seejärel **Retry deployment**

Ilma `AUTH_USER`/`AUTH_PASS` saladusteta ei lase leht kedagi sisse.

## Taustateenuse juhtimine

| Käsk | |
|---|---|
| `raadio` | olek, mida salvestab, järgmised salvestused, veebilehe aadress, viimased logiread |
| `raadio stop` / `start` / `restart` | |
| `raadio log` | logi reaalajas (Ctrl+C väljub) |
| `raadio url` | veebilehe aadress |
| `raadio test [sek] [jaam]` | testsalvestus, nt `raadio test 30 vikerraadio` |
| `raadio update` | uuenda uusimale versioonile (seaded ja salvestused jäävad alles) |
| `raadio parool` | näita kasutajanime, sea uus parool või eemalda see (ununenud parool) |

**Uuendused.** Salvesti kontrollib kord 12 tunni jooksul faili `https://raadio.mastering.ee/version.json` (muid andmeid ei saadeta). Kui on uuem versioon, näitavad seda veebileht („⬆ Uuendus saadaval“) ja `raadio`. Uuenda käsuga `raadio update` – see hoiatab, kui salvestus parasjagu käib. Kontrolli saab välja lülitada: `UPDATE_CHECK=0` seadete failis.

**Statistika.** raadio.mastering.ee loendab ainult päevaseid arve (lehe avamised, paigaldused, uuendused ja uuenduste kontrollid) – IP-aadresse ega muid isikuandmeid ei salvestata (`site/functions/`).

Taustateenus: macOS-is launchd (`~/Library/LaunchAgents/ee.raadiosalvestaja.plist`), Windowsis Task Scheduler (`Raadiosalvestaja`), Linuxis systemd kasutajateenus (`~/.config/systemd/user/raadiosalvestaja.service`, linger – käivitub ka ilma sisselogimiseta).
Logi: macOS `~/Library/Logs/raadiosalvestaja.log`, Windows `%LOCALAPPDATA%\Raadiosalvestaja\salvestaja.log`, Linux `~/.local/state/raadiosalvestaja/salvesti.log`.

## Arendus

```bash
cd web && npm install
printf 'AUTH_USER=test\nAUTH_PASS=test\nDEV_NO_AUTH=1\n' > .dev.vars
npm run dev    # http://localhost:8788, lokaalne R2 simulatsioon
```

Voo aadressid on failis `web/stations.json`. Kuku omad saab üle kirjutada ka failis `config.env` (`KUKU_STREAM_URL`, `KUKU_SCHEDULE_URL`).

Lokaalselt parooli vältimiseks lisa `.dev.vars` faili `DEV_NO_AUTH=1` (töötab ainult `localhost`-is).

## Litsents

MIT – vt [LICENSE](LICENSE). Litsents puudutab ainult koodi, mitte salvestatavat sisu.
