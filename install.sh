#!/usr/bin/env bash
# Ставит или обновляет все три проекта на сервере. Запуск:
#   curl -fsSL https://raw.githubusercontent.com/SavrOverSide/geekdigest/main/install.sh | sudo bash
set -euo pipefail

REPOS="geekdigest wordlore ideaforgegen"
DIR=/opt/tenge

if ! command -v docker >/dev/null || ! command -v git >/dev/null; then
  apt-get update -qq && apt-get install -y -qq docker.io git
  systemctl enable --now docker
fi

mkdir -p "$DIR" && cd "$DIR"
for r in $REPOS; do
  if [ -d "$r/.git" ]; then git -C "$r" pull -q; else git clone -q "https://github.com/SavrOverSide/$r"; fi
  [ -f "$r/.env" ] || cp "$r/.env.example" "$r/.env"
  chmod 600 "$r/.env"
  # Спрашиваем токен, только если его ещё нет. Ввод не показывается на экране.
  if grep -q '^BOT_TOKEN=$' "$r/.env"; then
    read -rsp "Вставь токен бота для $r и нажми Enter: " token < /dev/tty; echo
    sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=$token|" "$r/.env"
  fi
done

for r in $REPOS; do
  docker build -q -t "$r" "$r" >/dev/null
  docker rm -f "$r" >/dev/null 2>&1 || true
  extra=""
  [ "$r" = geekdigest ] && extra="-v $DIR:/tenge:ro"   # the evening owner report reads every bot's numbers (read-only)
  docker run -d --restart=always --env-file "$r/.env" -v "$DIR/$r/data:/app/data" $extra --name "$r" "$r" >/dev/null
  echo "✓ $r запущен"
done

echo
echo "Готово. Логи: docker logs -f wordlore (или geekdigest, ideaforgegen)."
echo "Настройки (время постов, OWNER_ID): nano $DIR/<проект>/.env, потом запусти этот скрипт ещё раз."
