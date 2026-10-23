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
        ("Гик-дайджест", "/app/data/digest.sqlite3")]
CHANNELS = ["@wordlores", "@ideaforges", "@geekdigests", "@geekdigest_eng"]


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


def report(now: float = None, root: Path = ROOT, channels: dict = None) -> str:
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
    if channels:
        lines.append("\n📣 Подписчики каналов: " + " · ".join(f"{ch} {n}" for ch, n in channels.items()))
    lines.append(f"\nИтого за день: +{total_new} новых, {total_stars} ⭐." +
                 ("" if total_new or total_stars else " Людей пока не прибавилось: им нужно узнать о ботах (claude/ПРОДВИЖЕНИЕ.md)."))
    return "\n".join(lines)


async def channel_counts(bot) -> dict:
    out = {}
    for ch in CHANNELS:
        try:
            out[ch] = await bot.get_chat_member_count(ch)
        except Exception:
            out[ch] = "?"
    return out


async def send_report(bot, owner: str) -> None:
    if owner.isdigit():
        await bot.send_message(int(owner), report(channels=await channel_counts(bot)), parse_mode="HTML")


def backup_zip(root: Path = ROOT, own: Path = Path("/app/data")) -> bytes:
    """A consistent snapshot of every bot's database, zipped (users, payments, premium, saved items)."""
    import io
    import tempfile
    import zipfile
    files = sorted(root.glob("*/data/*.sqlite3")) + sorted(own.glob("*.sqlite3"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, tempfile.TemporaryDirectory() as tmp:
        for f in files:
            snap = Path(tmp) / f.name
            src = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            dst = sqlite3.connect(snap)
            src.backup(dst)   # safe while the bot keeps writing
            src.close()
            dst.close()
            z.write(snap, f"{'geekdigest' if f.parent == own else f.parent.parent.name}/{f.name}")
    return buf.getvalue()


async def send_backup(bot, owner: str, now: float = None) -> bool:
    """Sundays only: the owner gets the databases as a file (restore: put them back into /opt/tenge/<bot>/data/)."""
    from aiogram.types import BufferedInputFile
    now = time.time() if now is None else now
    d = datetime.fromtimestamp(now, TZ)
    if d.weekday() != 6 or not owner.isdigit():
        return False
    data = backup_zip()
    await bot.send_document(int(owner), BufferedInputFile(data, filename=f"tenge-backup-{d:%Y-%m-%d}.zip"),
                            caption="🗄 Еженедельная копия баз ботов (пользователи, оплаты, премиумы). Сохрани файл; "
                                    "при переезде сервера его достаточно положить обратно в /opt/tenge/<бот>/data/.")
    return True
