"""Daily digest: collects fresh items from RSS feeds and posts one message to the channel.

Posted daily by run.py; one-off run:  python -m digest.digest [ru|en] [--dry-run]
Two editions, built from sources in their own language (no translation needed): ru -> CHANNEL, en -> CHANNEL_EN.
Subscribers who started the bot get the edition in their language as a direct message.
With ANTHROPIC_API_KEY each item is rewritten into one short sentence; without it headlines are used.
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
from aiogram.types import BufferedInputFile, LinkPreviewOptions

from common.config import DATA, env
from common.daily import TZ
from common.growth import broadcast, promo
from .card import render as render_cover
from .feeds import FEEDS

LANGS = ("ru", "en")


def seen_file(lang: str):
    return DATA / ("digest_seen.json" if lang == "ru" else f"digest_seen_{lang}.json")


PER_SECTION = 3
MAX_AGE = 36 * 3600


def clean(text: str, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def collect(seen: set, lang: str = "ru") -> dict:
    sections: dict[str, list] = {}
    now = time.time()
    for section, url in FEEDS[lang]:
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0 digest-bot")
        except Exception as e:  # one broken feed must not stop the digest
            print("feed failed", url, e, file=sys.stderr)
            continue
        for entry in feed.entries[:15]:
            link = re.sub(r"\?utm_[^#]*", "", entry.get("link") or "")  # tracking tail of the link is noise
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


def summarize(sections: dict, lang: str = "ru") -> dict:
    """Optionally rewrite each item into one Russian sentence via the Anthropic API."""
    key = env("ANTHROPIC_API_KEY")
    if not key:
        return {}
    items = [i for s in sections.values() for i in s]
    ask = {"ru": "Перескажи каждую новость одним коротким предложением на русском, без воды и кликбейта. ",
           "en": "Retell each news item in one short plain English sentence, no fluff or clickbait. "}[lang]
    prompt = (
        ask + "Верни JSON-массив строк в том же порядке (return a JSON array of strings in the same order).\n\n"
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


TITLE = {"ru": "Гик-дайджест", "en": "Geek Digest"}


def render(sections: dict, summaries: dict, lang: str = "ru") -> str:
    parts = [f"<b>{TITLE[lang]} · {time.strftime('%d.%m.%Y')}</b>"]
    for section, items in sections.items():
        parts.append(f"\n<b>{section}</b>")
        for i in items:
            text = html.escape(summaries.get(i["link"]) or i["title"])
            parts.append(f"• {text} <a href=\"{html.escape(i['link'])}\">→</a>")
    body = "\n".join(parts)
    footer = f"\n\n{promo('digest')}"
    return body + footer if len(body) + len(footer) < 4000 else body


async def send_edition(bot: Bot, chat, cover: bytes, text: str, top: str) -> None:
    """One edition to one chat: cover picture, then the digest with a large preview of the lead story."""
    try:  # the cover is a bonus: if it fails, the text digest still goes out
        await bot.send_photo(chat, BufferedInputFile(cover, filename="digest.jpg"))
    except Exception as e:
        if is_blocked(e):
            raise
        print("cover failed", e, file=sys.stderr)
    try:
        await bot.send_message(chat, text, parse_mode=ParseMode.HTML,
                               link_preview_options=LinkPreviewOptions(url=top, prefer_large_media=True, show_above_text=True))
    except Exception as e:  # never lose the digest over a preview problem
        if is_blocked(e):
            raise
        print("preview failed, sending plain", e, file=sys.stderr)
        await bot.send_message(chat, text, parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))


def is_blocked(e: Exception) -> bool:
    return type(e).__name__ in ("TelegramForbiddenError",)


async def main(dry_run: bool = False, langs=LANGS, store=None) -> None:
    """Builds each edition once and delivers it to its channel and to the subscribers of that language."""
    bot = None if dry_run else Bot(env("BOT_TOKEN"))
    try:
        for lang in langs:
            channel = env("CHANNEL") if lang == "ru" else env("CHANNEL_EN")
            subs = [u for u in (store.subs() if store else []) if (store.get_lang(u) or "ru") == lang]
            if not channel and not subs and not dry_run:
                continue
            f = seen_file(lang)
            seen = set(json.loads(f.read_text())) if f.exists() else set()
            sections = collect(seen, lang)
            if not sections:
                print(lang, "nothing new")
                continue
            summaries = summarize(sections, lang)
            text = render(sections, summaries, lang)
            if dry_run:
                print(text)
                continue
            cover = None
            try:
                cover = await asyncio.to_thread(render_cover, sections, summaries, datetime.now(TZ),
                                                env("HANDLE" if lang == "ru" else "HANDLE_EN", "@geekdigests"), lang)
            except Exception as e:
                print("cover failed", e, file=sys.stderr)
            top = next(iter(sections.values()))[0]["link"]  # lead story: Telegram shows its picture above the text

            async def deliver(chat):
                if cover:
                    await send_edition(bot, chat, cover, text, top)
                else:
                    await bot.send_message(chat, text, parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))

            if channel:
                try:
                    await deliver(channel)
                except Exception as e:
                    print("channel post failed", lang, e, file=sys.stderr)
            if subs:
                for uid in await broadcast(subs, deliver):
                    store.set_sub(uid, False)  # people who blocked the bot are unsubscribed
            seen |= {i["link"] for s in sections.values() for i in s}
            DATA.mkdir(exist_ok=True)
            f.write_text(json.dumps(sorted(seen)[-3000:]))
    finally:
        if bot:
            await bot.session.close()


if __name__ == "__main__":
    pick = [a for a in sys.argv[1:] if a in LANGS] or LANGS
    asyncio.run(main(dry_run="--dry-run" in sys.argv, langs=pick))
