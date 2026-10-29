# Raadiosalvesti konteineris (NAS: QNAP Container Station, Synology Container Manager, Unraid, TrueNAS jne).
# Kasutus: vt docker-compose.yml ja README („NAS / Docker“).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY recorder/requirements.txt recorder/requirements.txt
RUN pip install --no-cache-dir -r recorder/requirements.txt
COPY . .
RUN chmod +x recorder/docker-entrypoint.sh \
    && printf '#!/bin/sh\nexec python /app/recorder/raadio.py "$@"\n' > /usr/local/bin/raadio && chmod +x /usr/local/bin/raadio
ENV TZ=Europe/Tallinn PYTHONUNBUFFERED=1 RAADIO_CONF=/config/config.env RAADIO_DOCKER=1
VOLUME ["/data", "/config"]
EXPOSE 8788
ENTRYPOINT ["/app/recorder/docker-entrypoint.sh"]
