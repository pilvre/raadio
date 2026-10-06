#!/bin/zsh
# Raadiosalvesti paigaldus macOS-ile: venv, seaded, launchd teenus, `raadio` käsk.
# Mitteinteraktiivselt (nt CI): RAADIO_MODE=local|r2 RAADIO_PASS=... ./install.sh
set -e
DIR="${0:A:h}"
TTY=/dev/tty; [ -r /dev/tty ] || TTY=/dev/stdin
ask() { local __v; if [ -n "$RAADIO_NONINTERACTIVE" ]; then __v="$3"; else read "__v?$2" < $TTY || __v="$3"; fi; eval "$1=\"\${__v:-$3}\""; }

# olemasolev (vana nimega) paigaldus jääb samaks
LABEL=ee.raadiosalvestaja; [ -f ~/Library/LaunchAgents/ee.kuku.salvestaja.plist ] && LABEL=ee.kuku.salvestaja
LOG=~/Library/Logs/raadiosalvestaja.log; [ $LABEL = ee.kuku.salvestaja ] && LOG=~/Library/Logs/kuku-salvestaja.log
CONF_DIR=~/.config/raadiosalvestaja; [ -d ~/.config/kuku-salvestus ] && CONF_DIR=~/.config/kuku-salvestus
CONF=$CONF_DIR/config.env; [ -f $CONF_DIR/r2.env ] && [ ! -f $CONF ] && CONF=$CONF_DIR/r2.env
PLIST=~/Library/LaunchAgents/$LABEL.plist

command -v ffmpeg >/dev/null || { echo "ffmpeg puudub – paigalda: brew install ffmpeg"; exit 1; }

echo "→ Pythoni keskkond"
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$DIR/requirements.txt"

if [ ! -f "$CONF" ]; then
  mkdir -p "$CONF_DIR"
  cp "$DIR/config.env.example" "$CONF"
  chmod 600 "$CONF"
  if [ -z "$RAADIO_MODE" ]; then
    echo
    echo "Kus salvestusi hoida?"
    echo "  1) Siin arvutis (soovitatav – pilve pole vaja, telefonist koduvõrgus)"
    echo "  2) Cloudflare R2 (kuulamine kõikjal, vajab Cloudflare'i seadistamist)"
    ask mode "Valik [1]: " 1
    [ "$mode" = 2 ] && RAADIO_MODE=r2 || RAADIO_MODE=local
  fi
  if [ "$RAADIO_MODE" = r2 ]; then
    sed -i '' 's/^STORAGE=.*/STORAGE=r2/' "$CONF"
    echo "→ Täida R2 andmed failis $CONF ja käivita install.sh uuesti."
    [ -z "$RAADIO_NONINTERACTIVE" ] && open -e "$CONF" 2>/dev/null || true
    exit 0
  fi
  echo
  echo "Veebilehe sisselogimine (telefonis küsitakse kasutajanime ja parooli):"
  user="$RAADIO_USER"; [ -z "$user" ] && ask user "  Kasutajanimi [raadio]: " raadio
  pass="$RAADIO_PASS"; [ -z "$pass" ] && ask pass "  Parool (soovitatav, tühi = ilma parooliga): " ""
  # võivad sisaldada erimärke -> mitte sed-iga
  setconf() { VAL="$2" python3 -c 'import os,re,sys;p,k=sys.argv[1:3];s=open(p).read();open(p,"w").write(re.sub(r"(?m)^"+k+"=.*$",lambda m:k+"="+os.environ["VAL"],s))' "$CONF" "$1"; }
  setconf WEB_USER "${user:-raadio}"
  if [ -n "$pass" ]; then setconf WEB_PASS "$pass"; fi
fi
if grep -q "^STORAGE=r2" "$CONF" && ! grep -q "^R2_SECRET_ACCESS_KEY=..*" "$CONF"; then
  echo "Täida R2 andmed failis $CONF"; exit 1
fi

echo "→ Taustateenus (launchd)"
mkdir -p ~/Library/LaunchAgents ~/Library/Logs
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$DIR/.venv/bin/python</string>
    <string>-u</string>
    <string>$DIR/kuku_recorder.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$(dirname "$(command -v ffmpeg)"):/usr/bin:/bin:/usr/sbin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST
launchctl bootout gui/$(id -u)/$LABEL 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST"

chmod +x "$DIR/raadio" "$DIR/kuku"
if ! grep -q "alias raadio=" ~/.zshrc 2>/dev/null; then
  printf '\n# Raadiosalvesti\nalias raadio="\\"%s/raadio\\""\n' "$DIR" >> ~/.zshrc
  echo "→ Käsk 'raadio' lisatud (ava uus terminal)"
fi
sleep 4
echo
echo "✓ Valmis."
u=$("$DIR/.venv/bin/python" "$DIR/raadio.py" url)
case "$u" in http*)
  echo "  Ava telefonis (samas Wi-Fi võrgus): $u"
  if grep -q "^WEB_PASS=..*" "$CONF"; then
    echo "  Kasutajanimi: $(grep '^WEB_USER=' "$CONF" | cut -d= -f2- | grep . || echo raadio)   Parool: see, mille sisestasid"
  else
    echo "  (parool puudub – lehele pääseb igaüks samas võrgus)"
  fi;;
esac
echo
echo "  Salvesti oleku vaatamiseks ava uus Terminali aken ja kirjuta: raadio"
