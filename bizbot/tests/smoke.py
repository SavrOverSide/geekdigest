"""Booking bot on the real aiogram with a fake network. Run in the image:
docker run --rm -i -e ADMIN_IDS=900 -v $PWD/tests:/app/tests:ro bizbot python - < tests/smoke.py
"""
import asyncio
import sys
import time
from datetime import datetime

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/tests")

from real_aiogram import Harness, _ids  # noqa: E402
import bot as b  # noqa: E402

MONDAY_9 = datetime(2026, 10, 26, 9, 0, tzinfo=b.TZ).timestamp()   # a Monday, before opening
b.clock = lambda: MONDAY_9


async def contact(h, uid, phone):
    msg = {"message_id": next(_ids), "date": int(time.time()), "chat": {"id": uid, "type": "private"},
           "from": h._user(uid), "contact": {"phone_number": phone, "first_name": "Тест", "user_id": uid}}
    return await h._feed(f"{uid} shares contact", {"message": msg})


def names(calls):
    return [type(c).__name__ for c in calls]


async def main():
    h = Harness(b.router)
    calls = await h.say(1, "/start")
    for data in ("prices", "info", "my"):
        await h.press(1, data)
    # book: service -> master -> day -> time -> phone -> confirm
    calls = await h.press(1, "b:s")
    h.expect("s:cut" in h.buttons(calls), "services listed")
    calls = await h.press(1, "s:cut")
    h.expect("m:cut:*" in h.buttons(calls), "masters offered")
    calls = await h.press(1, "m:cut:a")
    day = next(x for x in h.buttons(calls) if x.startswith("d:cut:a:"))
    h.expect(day.endswith("261026"), f"today offered first ({day})")
    calls = await h.press(1, day)
    times = [x for x in h.buttons(calls) if x.startswith("t:")]
    h.expect(times[0].endswith(":1000"), f"first slot 10:00 ({times[0]})")
    h.expect(times[-1].endswith(":1900"), f"last slot fits before 20:00 ({times[-1]})")
    calls = await h.press(1, times[0])
    h.expect(any(type(c).__name__ == "SendMessage" and c.reply_markup and hasattr(c.reply_markup, "keyboard") for c in calls),
             "asks for phone with a contact button")
    calls = await contact(h, 1, "+77001234567")
    h.expect("ok" in h.buttons(calls), "confirmation screen")
    calls = await h.press(1, "ok")
    h.expect(any(getattr(c, "chat_id", None) == 900 for c in calls), "admin notified")
    h.expect(len(b.store.upcoming(uid=1, frm=0)) == 1, "booking saved")

    # the same master at 10:00 is now taken, the other master is free, "any master" still works
    calls = await h.press(2, day)
    h.expect(not any(x.endswith(":1000") for x in h.buttons(calls)), "taken slot hidden")
    calls = await h.press(2, "d:cut:d:261026")
    h.expect(any(x.endswith(":1000") for x in h.buttons(calls)), "other master free at 10:00")
    calls = await h.press(2, "t:cut:*:261026:1000")
    calls = await h.say(2, "+7 700 765 43 21")                     # phone typed as text
    calls = await h.press(2, "ok")
    bk = b.store.upcoming(uid=2, frm=0)
    h.expect(bk and bk[0]["master"] == "d", "any-master booking went to the free master")

    # a third person cannot get 10:00 with anyone now
    calls = await h.press(3, "d:cut:*:261026")
    h.expect(not any(x.endswith(":1000") for x in h.buttons(calls)), "10:00 fully booked")
    # Sunday is closed: never offered
    calls = await h.press(3, "m:cut:*")
    h.expect(not any(x.endswith("261101") for x in h.buttons(calls)), "closed day hidden")

    # reminders: two hours before
    b.clock = lambda: MONDAY_9 + 15 * 60
    sent = await b.send_reminders(h.bot)
    h.expect(sent == 2, f"two reminders sent ({sent})")
    h.expect(await b.send_reminders(h.bot) == 0, "reminders not repeated")

    # client cancels, admin sees schedule, admin cancels the other one
    calls = await h.press(1, f"c:{bk[0]['id'] - 1}")
    h.expect(any(getattr(c, "chat_id", None) == 900 for c in calls), "admin told about client cancel")
    calls = await h.say(900, "/today")
    h.expect(any("Данияр" in (getattr(c, "text", "") or "") for c in calls), "admin schedule shows booking")
    calls = await h.press(900, f"ac:{bk[0]['id']}")
    h.expect(any(getattr(c, "chat_id", None) == 2 for c in calls), "client told about admin cancel")
    calls = await h.press(5, f"ac:{bk[0]['id']}")                  # not an admin
    await h.say(900, "/stats")
    await h.say(900, "/week")
    calls = await h.say(5, "/today")
    h.expect(not calls, "non-admin gets nothing on /today")
    await h.say(5, "привет")
    await h.press(5, "zzz")
    h.report()


asyncio.run(main())
