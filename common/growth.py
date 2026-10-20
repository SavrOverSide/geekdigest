"""Growth helpers shared by the bots: invite links, share links, broadcasts, cross-promotion."""
import asyncio
import logging
from urllib.parse import quote

CHANNELS = {"digest": "@geekdigests", "words": "@wordlores", "ideas": "@ideaforges"}


def start_arg(text: str) -> str:
    """The payload of '/start <payload>' ('' if none)."""
    parts = (text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def ref_link(bot_username: str, uid: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{uid}"


def parse_ref(arg: str):
    """'ref_123' -> 123, anything else -> None."""
    if arg.startswith("ref_") and arg[4:].isdigit():
        return int(arg[4:])
    return None


def share_url(link: str, text: str = "") -> str:
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"


def promo(own: str) -> str:
    """One-line cross-promotion of the sibling channels (everything except `own`)."""
    others = " · ".join(handle for key, handle in CHANNELS.items() if key != own)
    return f"🔗 {others}"


async def broadcast(ids, send, per_second: int = 20):
    """Calls `await send(uid)` for each id, throttled. Returns the ids that should be dropped (blocked the bot)."""
    dead = []
    for n, uid in enumerate(ids):
        try:
            await send(uid)
        except Exception as e:  # blocked bot, deleted account, etc.
            name = type(e).__name__
            if "Forbidden" in name or "BadRequest" in name:
                dead.append(uid)
            else:
                logging.warning("broadcast to %s failed: %s", uid, e)
        if (n + 1) % per_second == 0:
            await asyncio.sleep(1.1)
    return dead
