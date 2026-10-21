"""Helpers for offline flow tests: a chat simulator on top of the fake aiogram."""
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests" / "fake_aiogram"))   # fake aiogram first
sys.path.insert(0, str(ROOT))

import common.config as cfg  # noqa: E402

_tmp = pathlib.Path(tempfile.mkdtemp())
cfg.DATA = _tmp
import common.db as dbm  # noqa: E402

dbm.DATA = _tmp

from aiogram import Bot  # noqa: E402
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, User  # noqa: E402


class Chat:
    """One user talking to the bot. Every message the bot sends is kept in `.log`."""

    def __init__(self, router, bot, uid, lang="ru"):
        self.router, self.bot, self.user = router, bot, User(uid, lang)
        self.log = []          # everything the bot produced, in order
        self.keyboards = []    # every inline keyboard shown

    def _collect(self, msg):
        for item in msg.out:
            self.log.append(item)
            check_message(item)
            kb = item.get("reply_markup")
            if kb is not None:
                self.keyboards.append(kb)
        msg.out.clear()

    async def say(self, text):
        m = Message(self.user, text, self.bot)
        handler = await self.router.feed("message", m)
        self._collect(m)
        return handler

    async def press(self, data, on=None):
        msg = on or Message(User(0), "", self.bot)
        c = CallbackQuery(self.user, data, msg, self.bot)
        handler = await self.router.feed("callback_query", c)
        self._collect(msg)
        c.handler = handler
        return c

    def buttons(self):
        return [b for kb in self.keyboards for row in kb.inline_keyboard for b in row]

    def last(self):
        return self.log[-1]

    async def pay(self, payload, stars, charge=None):
        charge = charge or f"ch{self.user.id}-{len(self.log)}-{time.time_ns()}"
        q = PreCheckoutQuery(payload, stars)
        await self.router.feed("pre_checkout_query", q)
        sp = type("SP", (), {"telegram_payment_charge_id": charge, "total_amount": stars, "invoice_payload": payload})()
        m = Message(self.user, "", self.bot, successful_payment=sp)
        await self.router.feed("message", m)
        self._collect(m)
        return q.result


def route_of(router, data):
    """Name of the handler that would receive a callback with this data (without running it)."""
    probe = CallbackQuery(User(0), data, Message(User(0)), None)

    def walk(r):
        for kind, filters, fn in r.handlers:
            if kind == "callback_query" and all(f(probe) for f in filters):
                return fn.__name__
        for child in r.children:
            found = walk(child)
            if found:
                return found
        return None

    return walk(router)


def assert_buttons_routable(test, chat):
    for b in chat.buttons():
        if b.callback_data is not None:
            test.assertLessEqual(len(b.callback_data.encode()), 64, b.callback_data)
            name = route_of(chat.router, b.callback_data)
            test.assertNotIn(name, (None, "stale_button"), f"dead button {b.text!r} -> {b.callback_data!r}")


def check_message(item):
    """Rules Telegram enforces that a fake can't: HTML only renders with parse_mode, length limits, no unfilled {placeholders}."""
    body = item.get("text") or item.get("caption") or ""
    limit = 1024 if item["kind"] == "photo" else 4096
    assert len(body) <= limit, f"message too long ({len(body)}): {body[:60]!r}"
    if "<b>" in body or "<a " in body or "<i>" in body:
        assert item.get("parse_mode") == "HTML", f"HTML tags without parse_mode: {body[:80]!r}"
    import re
    assert not re.search(r"\{\w+\}", body), f"unfilled placeholder: {body[:80]!r}"
