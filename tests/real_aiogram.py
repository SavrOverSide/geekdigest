"""Drives the real aiogram Dispatcher with a fake network, to check routing and API calls end to end.

Not part of the offline unit tests (needs aiogram installed). Run inside the bot's Docker image, which has
a fresh empty /app/data volume, e.g.:  docker run --rm -i wordlore python - < tests/real_smoke.py
"""
import itertools
import time
import typing

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Message, User

_ids = itertools.count(1000)


class FakeSession(BaseSession):
    """Records every API method and answers with a plausible object of the type aiogram expects."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        ret = str(getattr(method, "__returning__", ""))
        name = type(method).__name__
        if name == "GetMe":
            return User(id=1, is_bot=True, first_name="Test", username="test_bot")
        if "Message" in ret:
            chat_id = getattr(method, "chat_id", 1)
            chat = {"id": chat_id if isinstance(chat_id, int) else -100, "type": "private" if isinstance(chat_id, int) else "channel"}
            return Message.model_validate({"message_id": next(_ids), "date": int(time.time()), "chat": chat, "text": "x"},
                                          context={"bot": bot})
        if "list" in ret.lower():
            return []
        return True

    async def stream_content(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    async def close(self):
        pass


class Harness:
    def __init__(self, router):
        self.session = FakeSession()
        self.bot = Bot("123456:TEST", session=self.session)
        self.dp = Dispatcher()
        self.dp.include_router(router)
        self.uid = itertools.count(1)
        self.failures = []

    def _user(self, uid, lang="ru", name="Тест"):
        return {"id": uid, "is_bot": False, "first_name": name, "language_code": lang}

    async def _feed(self, label, update):
        before = len(self.session.calls)
        try:
            res = await self.dp.feed_raw_update(self.bot, {"update_id": next(self.uid), **update})
        except Exception as e:  # a crash inside a handler
            self.failures.append(f"{label}: CRASH {type(e).__name__}: {e}")
            return []
        new = self.session.calls[before:]
        if res is UNHANDLED:
            self.failures.append(f"{label}: nobody handled it")
        print(f"  {'ok ' if res is not UNHANDLED else 'NO '} {label:<34} -> {', '.join(type(c).__name__ for c in new) or '(nothing)'}")
        return new

    async def say(self, uid, text, lang="ru", name="Тест"):
        msg = {"message_id": next(_ids), "date": int(time.time()), "chat": {"id": uid, "type": "private"},
               "from": self._user(uid, lang, name), "text": text}
        return await self._feed(f"{uid} says {text[:24]!r}", {"message": msg})

    async def press(self, uid, data, lang="ru"):
        msg = {"message_id": next(_ids), "date": int(time.time()), "chat": {"id": uid, "type": "private"}, "text": "x",
               "from": {"id": 1, "is_bot": True, "first_name": "Test"}}
        cq = {"id": str(next(_ids)), "from": self._user(uid, lang), "chat_instance": "c", "data": data, "message": msg}
        return await self._feed(f"{uid} presses {data[:24]!r}", {"callback_query": cq})

    async def pre_checkout(self, uid, payload, stars):
        q = {"id": str(next(_ids)), "from": self._user(uid), "currency": "XTR", "total_amount": stars, "invoice_payload": payload}
        return await self._feed(f"{uid} pre-checkout {payload}", {"pre_checkout_query": q})

    async def paid(self, uid, payload, stars):
        msg = {"message_id": next(_ids), "date": int(time.time()), "chat": {"id": uid, "type": "private"}, "from": self._user(uid),
               "successful_payment": {"currency": "XTR", "total_amount": stars, "invoice_payload": payload,
                                      "telegram_payment_charge_id": f"ch{next(_ids)}", "provider_payment_charge_id": ""}}
        return await self._feed(f"{uid} paid {payload}", {"message": msg})

    @staticmethod
    def buttons(calls) -> typing.List[str]:
        out = []
        for c in calls:
            kb = getattr(c, "reply_markup", None)
            for row in getattr(kb, "inline_keyboard", None) or []:
                for b in row:
                    out.append(b.callback_data or b.url or "")
        return out

    def expect(self, cond, label):
        if not cond:
            self.failures.append(label)

    def report(self):
        print()
        if self.failures:
            print("FAILURES:")
            for f in self.failures:
                print("  -", f)
            raise SystemExit(1)
        print("ALL GOOD")
