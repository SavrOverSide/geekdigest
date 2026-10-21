"""Real-aiogram smoke run for the digest bot (see tests/real_aiogram.py)."""
import asyncio
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/tests")

from real_aiogram import Harness  # noqa: E402
from digest import bot as db  # noqa: E402


async def main():
    h = Harness(db.router)
    for lang in ("ru", "en"):
        calls = await h.say(10 if lang == "ru" else 11, "/start", lang=lang)
        h.expect(any(type(c).__name__ == "SendMessage" for c in calls), f"/start {lang}")
        urls = [b for b in h.buttons(calls) if b.startswith("http")]
        h.expect(any("t.me/" in u for u in urls), f"channel link {lang}")
    calls = await h.press(10, "sub")
    h.expect(db.store.is_sub(10), "subscribed")
    await h.press(10, "lang")
    h.expect(db.store.get_lang(10) == "en", "language switched")
    for cmd in ("/sub", "/lang", "/help"):
        calls = await h.say(12, cmd)
        h.expect(bool(calls), f"{cmd} replies")
    calls = await h.press(12, "old:button")
    h.expect(any(type(c).__name__ == "AnswerCallbackQuery" and c.show_alert for c in calls), "stale button explained")
    h.report()


asyncio.run(main())
