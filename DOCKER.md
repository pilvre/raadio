# Raadiosalvesti Dockeri juhend

See juhend kirjeldab Raadiosalvesti käivitamist turvalises, minimaalses Alpine-põhises Dockeri konteineris suvalises Linux-serveris.

## Omadused ja turvalisus

- **Väike baastõmmis**: Alpine Linux (`python:3.12-alpine`) koos vajalike süsteemsete tööriistadega (`ffmpeg`, `tzdata`).
- **Tavakasutaja õigused**: Konteiner ei jookse root-kasutajana, vaid madalate privileegidega kasutajana `raadio` (UID `1000`, GID `1000`).
- **Read-only failisüsteem**: Konteineri juurfailisüsteem on täielikult kirjutuskaitstud (`read_only: true`).
- **Mälupõhine ajutine failisüsteem**: Tööfailid ja ffmpeg salvestuspuhvrid luuakse RAM-is (`tmpfs: /tmp`).
- **Andmete püsivus (Volumes)**: Salvestused, saatekavad ja konfiguratsioon salvestatakse püsivale kettamahu jaotisele (`/data`).
- **Pöördproksi valmisolek (Traefik, Nginx, Caddy)**: Toetab `X-Forwarded-*` päiseid ja automaatseid HTTPS linke podcasti feedides (`PUBLIC_URL`).

---

## 1. Kiirkäivitus Docker Compose'iga

1. Klooni repositoorium või lae alla failid `docker-compose.yml` ja `Dockerfile`:
   ```bash
   git clone https://github.com/pilvre/raadio.git
   cd raadio
   ```

2. Valmista ette andmekataloog ja määra õigused kasutajale UID 1000:
   ```bash
   mkdir -p data
   sudo chown -R 1000:1000 data
   ```

3. Käivita teenus:
   ```bash
   docker compose up -d
   ```

4. Ava brauseris:
   `http://<serveri-ip>:8788`

---

## 2. Pöördproksi seadistamine (Reverse Proxy)

Konteineri veebiserver töötab pordil `8788` ning toetab `X-Forwarded-Host` ja `X-Forwarded-Proto` päiseid.

### A. Traefik (v2 / v3)

Kui sul töötab Traefik (nt võrgus `traefik_network`), seadista `docker-compose.yml`:

```yaml
services:
  raadio:
    image: raadiosalvesti:latest
    build: .
    container_name: raadiosalvesti
    restart: unless-stopped
    user: "1000:1000"
    read_only: true
    init: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    tmpfs:
      - /tmp:size=512M
    environment:
      - TZ=Europe/Tallinn
      - STORAGE=local
      - LOCAL_DIR=/data
      - WEB_PORT=8788
      - WEB_USER=raadio
      - WEB_PASS=minu_parool
      - PUBLIC_URL=https://raadio.sinudomeen.ee
    volumes:
      - ./data:/data
    networks:
      - traefik_network
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.raadio.rule=Host(`raadio.sinudomeen.ee`)"
      - "traefik.http.routers.raadio.entrypoints=websecure"
      - "traefik.http.routers.raadio.tls.certresolver=myresolver"
      - "traefik.http.services.raadio.loadbalancer.server.port=8788"

networks:
  traefik_network:
    external: true
```

> **Autentimise nipp:** Kui soovid kasutada Traefiku enda BasicAuth / Authelia / Authentik middleware'i, jäta `WEB_PASS` tühjaks, et vältida kahekordset sisselogimist.

### B. Nginx

```nginx
server {
    server_name raadio.sinudomeen.ee;

    location / {
        proxy_pass http://127.0.0.1:8788;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Vajalik helivoo kerimiseks (HTTP Range päised)
        proxy_force_ranges on;
    }
}
```

### C. Caddy

```caddy
raadio.sinudomeen.ee {
    reverse_proxy 127.0.0.1:8788
}
```

---

## 3. Käivitamine käsuga `docker run`

Kui eelistad käsurealt otse `docker run` käsku:

```bash
docker run -d \
  --name raadiosalvesti \
  --restart unless-stopped \
  --read-only \
  --init \
  --user 1000:1000 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:size=512M \
  -e TZ=Europe/Tallinn \
  -e STORAGE=local \
  -e WEB_USER=raadio \
  -e WEB_PASS=minu_parool \
  -e PUBLIC_URL=https://raadio.sinudomeen.ee \
  -v $(pwd)/data:/data \
  -p 8788:8788 \
  raadiosalvesti:latest
```

---

## 4. Keskkonnamuutujad

| Muutuja | Vaikimisi | Kirjeldus |
|---|---|---|
| `STORAGE` | `local` | Salvestuskiht: `local` (kettale) või `r2` (Cloudflare R2). |
| `LOCAL_DIR` | `/data` | Kohalike salvestuste kaust konteineris. |
| `WEB_PORT` | `8788` | Veebiserveri port konteineri sees. |
| `WEB_USER` | `raadio` | Veebiliidese kasutajanimi. |
| `WEB_PASS` | *(tühi)* | Veebiliidese parool. Tühjana pääseb ligi paroolita. |
| `PUBLIC_URL` | *(tühi)* | Serveri avalik aadress (nt `https://raadio.sinudomeen.ee`), kasutatakse taskuhäälingu RSS-feedides. |
| `TZ` | `Europe/Tallinn` | Konteineri ajavöönd. Oluline õigete saateaegade salvestamiseks! |
| `RAADIO_STATE_DIR` | `/data/.state` | Eelnevate salvestuste seisu (`done.json`) faili asukoht. |
| `UPDATE_CHECK` | `1` | Kontrolli uute versioonide olemasolu (`0` lülitab välja). |
| `R2_ENDPOINT` | *(tühi)* | Cloudflare R2 endpoint (`STORAGE=r2` puhul). |
| `R2_BUCKET` | `raadio` | R2 bucket nimi. |
| `R2_ACCESS_KEY_ID` | *(tühi)* | R2 Access Key. |
| `R2_SECRET_ACCESS_KEY` | *(tühi)* | R2 Secret Key. |

---

## 5. Haldamine ja utiliit `raadio`

Konteineri sees on olemas sama `raadio` haldustööriist:

- **Vaata salvesti olekut ja eelseisvaid salvestusi:**
  ```bash
  docker compose exec raadio raadio status
  ```

- **Tee 30-sekundiline testsalvestus (nt Vikerraadio):**
  ```bash
  docker compose exec raadio raadio test 30 vikerraadio
  ```

- **Vaata reaalajas logi:**
  ```bash
  docker compose logs -f
  ```
