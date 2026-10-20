"""Daily digest: collects fresh items from RSS feeds and posts one message to the channel.

Posted daily by run.py; one-off run:  python -m digest.digest [--dry-run]
Without ANTHROPIC_API_KEY it posts headlines with links; with the key it writes short Russian summaries.
"""
import asyncio
import html
import json
import re
import sys
import time
import urllib.request

import feedparser
from datetime import datetime

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

from common.config import DATA, env
from common.daily import TZ
from .card import render as render_cover
from .feeds import FEEDS

SEEN = DATA / "digest_seen.json"
PER_SECTION = 3
MAX_AGE = 36 * 3600


def clean(text: str, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def collect(seen: set) -> dict:
    sections: dict[str, list] = {}
    now = time.time()
    for section, url in FEEDS:
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0 digest-bot")
        except Exception as e:  # one broken feed must not stop the digest
            print("feed failed", url, e, file=sys.stderr)
            continue
        for entry in feed.entries[:15]:
            link = entry.get("link")
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            if not link or link in seen or (stamp and now - time.mktime(stamp) > MAX_AGE):
                continue
            items = sections.setdefault(section, [])
            if len(items) < PER_SECTION:
                items.append({
                    "title": clean(entry.get("title", ""), 140),
                    "summary": clean(entry.get("summary", ""), 400),
                    "link": link,
                })
    return sections


def summarize(sections: dict) -> dict:
    """Optionally rewrite each item into one Russian sentence via the Anthropic API."""
    key = env("ANTHROPIC_API_KEY")
    if not key:
        return {}
    items = [i for s in sections.values() for i in s]
    prompt = (
        "Перескажи каждую новость одним коротким предложением на русском, без воды и кликбейта. "
        "Верни JSON-массив строк в том же порядке.\n\n"
        + "\n".join(f"{n}. {i['title']} — {i['summary']}" for n, i in enumerate(items, 1))
    )
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": env("ANTHROPIC_MODEL", "claude-haiku-5-5"),
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = json.load(r)["content"][0]["text"]
        lines = json.loads(text[text.index("["): text.rindex("]") + 1])
        return {i["link"]: str(line) for i, line in zip(items, lines)}
    except Exception as e:
        print("summary failed, posting headlines", e, file=sys.stderr)
        return {}


def render(sections: dict, summaries: dict) -> str:
    parts = [f"<b>Гик-дайджест · {time.strftime('%d.%m.%Y')}</b>"]
    for section, items in sections.items():
        parts.append(f"\n<b>{section}</b>")
        for i in items:
            text = html.escape(summaries.get(i["link"]) or i["title"])
            parts.append(f"• {text} <a href=\"{html.escape(i['link'])}\">→</a>")
    return "\n".join(parts)


async def main(dry_run: bool = False) -> None:
    seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()
    sections = collect(seen)
    if not sections:
        print("nothing new")
        return
    summaries = summarize(sections)
    text = render(sections, summaries)
    if dry_run:
        print(text)
        return
    bot = Bot(env("BOT_TOKEN"))
    try:
        try:  # the cover is a bonus: if it fails, the text digest still goes out
            cover = await asyncio.to_thread(render_cover, sections, summaries, datetime.now(TZ))
            await bot.send_photo(env("CHANNEL"), BufferedInputFile(cover, filename="digest.jpg"))
        except Exception as e:
            print("cover failed", e, file=sys.stderr)
        await bot.send_message(env("CHANNEL"), text, parse_mode=ParseMode.HTML,
                               disable_web_page_preview=True)
    finally:
        await bot.session.close()
    seen |= {i["link"] for s in sections.values() for i in s}
    DATA.mkdir(exist_ok=True)
    SEEN.write_text(json.dumps(sorted(seen)[-3000:]))


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
