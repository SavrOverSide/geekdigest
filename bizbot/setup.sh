#!/usr/bin/env bash
# Starts (or updates) a booking bot for one client. Usage on the server:
#   bash /opt/tenge/geekdigest/bizbot/setup.sh <client-name>
# First run asks for the bot token and the admin Telegram IDs; config is /opt/tenge/clients/<client-name>/config.json
set -euo pipefail
NAME=${1:?client name, e.g. borodabarber}
SRC=/opt/tenge/geekdigest/bizbot
DIR=/opt/tenge/clients/$NAME
mkdir -p "$DIR/data"
[ -f "$DIR/config.json" ] || cp "$SRC/config.json" "$DIR/config.json"
if [ ! -f "$DIR/.env" ]; then
  read -rsp "Токен бота для $NAME: " token < /dev/tty; echo
  read -rp "Telegram ID администраторов через запятую: " ids < /dev/tty
  printf 'BOT_TOKEN=%s\nADMIN_IDS=%s\nCONFIG=/app/client/config.json\nDATA_DIR=/app/data\n' "$token" "$ids" > "$DIR/.env"
  chmod 600 "$DIR/.env"
fi
docker build -q -t bizbot "$SRC" >/dev/null
docker rm -f "biz-$NAME" >/dev/null 2>&1 || true
docker run -d --restart=always --env-file "$DIR/.env" -v "$DIR/data:/app/data" -v "$DIR:/app/client:ro" --name "biz-$NAME" bizbot >/dev/null
echo "✓ biz-$NAME запущен. Настройки: nano $DIR/config.json, потом снова этот скрипт. Логи: docker logs -f biz-$NAME"
