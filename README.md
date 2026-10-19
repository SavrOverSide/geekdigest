# Гик-дайджест

Каждый день в 09:00 по Казахстану публикует в [@geekdigests](https://t.me/geekdigests) свежие новости ИИ, игр, техники и науки из RSS-лент ([digest/feeds.py](digest/feeds.py)).

## Установка на сервер (все три проекта сразу)

```bash
curl -fsSL https://raw.githubusercontent.com/SavrOverSide/geekdigest/main/install.sh | sudo bash
```

Скрипт поставит Docker, скачает `geekdigest`, `wordlore` и `ideaforgegen` в `/opt/tenge`, спросит токены трёх ботов и запустит их. Повторный запуск обновляет код до последней версии.

Проверить пост без публикации: `docker exec geekdigest python -m digest.digest --dry-run`
