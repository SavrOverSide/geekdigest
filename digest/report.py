"""Evening report for the owner: how every project did today, read straight from the bots' databases (read-only).

The installer mounts /opt/tenge read-only at /tenge inside this container.
"""
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from common.daily import TZ

ROOT = Path("/tenge")
BOTS = [("Wordlore", "wordlore/data/lingvo.sqlite3"), ("IdeaForge", "ideaforgegen/data/ideas.sqlite3"),
        ("Гик-дайджест", "geekdigest/data/digest.sqlite3")]


def _one(c, q, args=()):
    try:
        return c.execute(q, args).fetchone()[0] or 0
    except sqlite3.Error:
        return 0  # an older database may not have the table yet


def bot_numbers(path: Path, now: float) -> dict:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    day = datetime.fromtimestamp(now, TZ).date()
    start = datetime.combine(day, datetime.min.time(), TZ).timestamp()
    try:
        return {
            "users": _one(c, "SELECT COUNT(*) FROM users"),
            "new": _one(c, "SELECT COUNT(*) FROM users WHERE created >= ?", (int(start),)),
            "active": _one(c, "SELECT COUNT(DISTINCT user_id) FROM activity WHERE day = ?", (day.isoformat(),)),
            "week": _one(c, "SELECT COUNT(DISTINCT user_id) FROM activity WHERE day >= ?", ((day - timedelta(days=6)).isoformat(),)),
            "stars_today": _one(c, "SELECT SUM(stars) FROM payments WHERE at >= ?", (int(start),)),
            "stars": _one(c, "SELECT SUM(stars) FROM payments"),
            "subs": _one(c, "SELECT COUNT(*) FROM subs"),
        }
    finally:
        c.close()


def report(now: float = None, root: Path = ROOT) -> str:
    now = time.time() if now is None else now
    lines = [f"📊 Итоги дня · {datetime.fromtimestamp(now, TZ):%d.%m}"]
    total_new = total_stars = 0
    for name, rel in BOTS:
        path = root / rel
        if not path.exists():
            lines.append(f"\n{name}: база не найдена")
            continue
        n = bot_numbers(path, now)
        total_new += n["new"]
        total_stars += n["stars_today"]
        lines.append(f"\n<b>{name}</b>\n👥 {n['users']} всего, +{n['new']} сегодня · активных сегодня {n['active']}, за 7 дней {n['week']}\n"
                     f"⭐ сегодня {n['stars_today']}, всего {n['stars']} · 🔔 рассылка {n['subs']}")
    lines.append(f"\nИтого за день: +{total_new} новых, {total_stars} ⭐." +
                 ("" if total_new or total_stars else " Людей пока не прибавилось: им нужно узнать о ботах (claude/ПРОДВИЖЕНИЕ.md)."))
    return "\n".join(lines)


async def send_report(bot, owner: str) -> None:
    if owner.isdigit():
        await bot.send_message(int(owner), report(), parse_mode="HTML")
