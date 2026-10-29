#!/bin/sh
# Konteineri käivitus: seaded failis /config/config.env (luuakse esimesel korral), salvestused /data.
# Keskkonnamuutujad (docker-compose.yml) kirjutatakse igal käivitusel seadetesse:
#   RAADIO_USER, RAADIO_PASS – veebilehe kasutajanimi ja parool
#   RAADIO_HOST – NAS-i aadress (nt 192.168.1.10), et salvesti näitaks õiget veebilehe aadressi
set -e
CONF=${RAADIO_CONF:-/config/config.env}
mkdir -p "$(dirname "$CONF")" /data
if [ ! -f "$CONF" ]; then
  sed -e 's|^LOCAL_DIR=.*|LOCAL_DIR=/data|' /app/recorder/config.env.example > "$CONF"
  chmod 600 "$CONF"
  echo "seaded loodud: $CONF"
fi
setconf() { VAL="$2" python -c 'import os,re,sys
p,k=sys.argv[1:3];s=open(p).read();v=os.environ["VAL"]
s=re.sub(r"(?m)^"+k+"=.*$",lambda m:k+"="+v,s) if re.search(r"(?m)^"+k+"=",s) else s.rstrip("\n")+"\n"+k+"="+v+"\n"
open(p,"w").write(s)' "$CONF" "$1"; }
[ -n "$RAADIO_USER" ] && setconf WEB_USER "$RAADIO_USER"
[ -n "$RAADIO_PASS" ] && setconf WEB_PASS "$RAADIO_PASS"
grep -q "^LOCAL_DIR=" "$CONF" || setconf LOCAL_DIR /data
exec python -u /app/recorder/kuku_recorder.py
