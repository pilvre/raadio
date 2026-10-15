# syntax=docker/dockerfile:1
FROM python:3.12-alpine

LABEL org.opencontainers.image.title="Raadiosalvesti" \
      org.opencontainers.image.description="Isiklik raadiosaadete salvesti ja veebipleier" \
      org.opencontainers.image.licenses="MIT"

# Paigaldame ainult vajaliku: ffmpeg voogude salvestamiseks, tzdata ajavööndi jaoks
RUN apk add --no-cache ffmpeg tzdata

# Loome tavakasutaja (mitte-root) UID/GID 1000
RUN addgroup -g 1000 -S raadio && \
    adduser -u 1000 -S raadio -G raadio -h /home/raadio

WORKDIR /app

# Paigaldame Pythoni sõltuvused (eraldi kihina parema vahemälu kasutuse tagamiseks)
COPY recorder/requirements.txt /app/recorder/requirements.txt
RUN pip install --no-cache-dir -r /app/recorder/requirements.txt

# Kopeerime salvesti koodi ja veebiliidese
COPY recorder/ /app/recorder/
COPY web/ /app/web/
COPY VERSION* /app/

# Teeme juhtkäsu 'raadio' kättesaadavaks (nt: docker exec -it raadio raadio status)
RUN ln -sf /app/recorder/raadio.py /usr/local/bin/raadio && \
    chmod +x /app/recorder/raadio.py /usr/local/bin/raadio

# Valmistame ette andme- ja seadistuskataloogid tavakasutaja õigustes
RUN mkdir -p /data /config /home/raadio/.local/share /home/raadio/.config && \
    chown -R raadio:raadio /app /data /config /home/raadio

# Vaikimisi keskkonnamuutujad
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Tallinn \
    STORAGE=local \
    LOCAL_DIR=/data \
    RAADIO_STATE_DIR=/data/.state \
    WEB_PORT=8788

# Tavakasutaja õigused
USER 1000:1000

# Salvestuste ja konfiguratsiooni andmemaht
VOLUME ["/data"]

EXPOSE 8788

# Tervisekontroll (toimib ka parooliga kaitstud veebiserveri korral)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python3", "-c", "import http.client, sys; c = http.client.HTTPConnection('127.0.0.1', 8788, timeout=4); c.request('GET', '/api/schedule'); sys.exit(0 if c.getresponse().status in (200, 401) else 1)"]

CMD ["python3", "/app/recorder/kuku_recorder.py"]
