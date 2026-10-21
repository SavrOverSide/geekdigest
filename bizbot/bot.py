"""Booking bot for a small service business (barbershop, salon, clinic, studio).

Everything business-specific lives in config.json: name, address, hours, services, masters.
Clients book in a few taps; admins (ADMIN_IDS) get every booking and can cancel; clients get a reminder.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove)

from store import Store

HERE = Path(__file__).parent
CFG = json.loads(Path(os.environ.get("CONFIG", HERE / "config.json")).read_text(encoding="utf-8"))
TZ = timezone(timedelta(hours=CFG.get("utc_offset", 5)))
SERVICES = {s["id"]: s for s in CFG["services"]}
MASTERS = {m["id"]: m for m in CFG.get("masters", [])}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
PHONE = re.compile(r"^\+?[\d\s\-()]{10,18}$")

store = Store(Path(os.environ.get("DATA_DIR", HERE / "data")) / "bookings.sqlite3")
router = Router()
PENDING: dict = {}       # user id -> {"sid", "mid", "start"} while the booking is being confirmed
clock = time.time        # replaced in tests


def admins() -> set:
    return {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}


def btn(text, data="", url=""):
    return InlineKeyboardButton(text=text, url=url) if url else InlineKeyboardButton(text=text, callback_data=data)


def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def when(ts: int) -> str:
    d = datetime.fromtimestamp(ts, TZ)
    return f"{WD[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}, {d:%H:%M}"


def master_name(mid: str) -> str:
    return MASTERS[mid]["name"] if mid in MASTERS else ""


def service_name(sid: str) -> str:
    return "⛔ Занято" if sid == "block" else SERVICES.get(sid, {"name": sid})["name"]


def describe(b: dict) -> str:
    s = {"name": service_name(b["service"])}
    who = f" · мастер {master_name(b['master'])}" if b["master"] else ""
    return f"{s['name']}{who}\n🗓 {when(b['start'])}"


# ---- schedule -------------------------------------------------------------------------------
def days() -> list:
    """Open days from today on, as (yymmdd, label)."""
    today = datetime.fromtimestamp(clock(), TZ).date()
    out = []
    for i in range(CFG.get("days_ahead", 7)):
        d = today + timedelta(days=i)
        if CFG["hours"].get(DAYS[d.weekday()]) and not store.is_closed(d.strftime("%y%m%d")):
            label = "Сегодня" if i == 0 else "Завтра" if i == 1 else f"{WD[d.weekday()].capitalize()} {d.day:02d}.{d.month:02d}"
            out.append((d.strftime("%y%m%d"), label))
    return out


def slots(day: str, sid: str, mid: str) -> list:
    """Free start times (unix) for a service on a day. mid '*' = any master, '-' = no masters at all."""
    d = datetime.strptime(day, "%y%m%d").date()
    hours = CFG["hours"].get(DAYS[d.weekday()])
    if not hours or store.is_closed(day):
        return []
    minutes = SERVICES[sid]["minutes"]
    open_t, close_t = (datetime.combine(d, datetime.strptime(h, "%H:%M").time(), TZ).timestamp() for h in hours)
    step = CFG.get("slot_minutes", 30) * 60
    earliest = clock() + 30 * 60          # no bookings for the next half hour
    out, t = [], open_t
    while t + minutes * 60 <= close_t:
        if t >= earliest and free_master(mid, int(t), minutes) is not None:
            out.append(int(t))
        t += step
    return out


def free_master(mid: str, start: int, minutes: int):
    """The master who can take this slot ('' when the business has no masters), or None."""
    end = start + minutes * 60
    if not MASTERS:
        return "" if not store.busy("", start, end) else None
    candidates = list(MASTERS) if mid == "*" else [mid]
    return next((m for m in candidates if m in MASTERS and not store.busy(m, start, end)), None)


# ---- screens ---------------------------------------------------------------------------------
def main_menu() -> InlineKeyboardMarkup:
    return kb([btn("📅 Записаться", "b:s")], [btn("💈 Услуги и цены", "prices"), btn("📍 Адрес", "info")],
              [btn("📋 Мои записи", "my")])


@router.message(CommandStart())
async def start(m: Message):
    store.touch_client(m.from_user.id, m.from_user.first_name or "")
    await m.answer(f"👋 <b>{CFG['name']}</b>\n\n{CFG['about']}", parse_mode="HTML", reply_markup=main_menu())


@router.callback_query(F.data == "prices")
async def prices(c: CallbackQuery):
    lines = [f"• {s['name']}: <b>{s['price']}</b> ({s['minutes']} мин)" for s in CFG["services"]]
    await c.message.answer("💈 <b>Услуги и цены</b>\n\n" + "\n".join(lines), parse_mode="HTML",
                           reply_markup=kb([btn("📅 Записаться", "b:s")]))
    await c.answer()


@router.callback_query(F.data == "info")
async def info(c: CallbackQuery):
    hours = []
    for i, key in enumerate(DAYS):
        h = CFG["hours"].get(key)
        hours.append(f"{WD[i]}: {h[0]}–{h[1]}" if h else f"{WD[i]}: выходной")
    text = f"📍 {CFG['address']}\n📞 {CFG['phone']}\n\n🕒 " + "\n🕒 ".join(hours)
    await c.message.answer(text, reply_markup=kb([btn("🗺 Открыть карту", url=CFG["map_url"])] if CFG.get("map_url") else None,
                                                  [btn("📅 Записаться", "b:s")]))
    await c.answer()


@router.callback_query(F.data == "b:s")
async def choose_service(c: CallbackQuery):
    rows = [[btn(f"{s['name']} · {s['price']}", f"s:{s['id']}")] for s in CFG["services"]]
    await c.message.answer("Что делаем?", reply_markup=kb(*rows))
    await c.answer()


@router.callback_query(F.data.startswith("s:"))
async def choose_master(c: CallbackQuery):
    sid = c.data[2:]
    if sid not in SERVICES:
        return await c.answer()
    if not MASTERS:
        return await show_days(c, sid, "-")
    rows = [[btn("Любой свободный мастер", f"m:{sid}:*")]] + [[btn(m["name"], f"m:{sid}:{m['id']}")] for m in CFG["masters"]]
    await c.message.edit_text(f"{SERVICES[sid]['name']}. К кому записать?", reply_markup=kb(*rows, [btn("← Назад", "b:s")]))
    await c.answer()


@router.callback_query(F.data.startswith("m:"))
async def pick_master(c: CallbackQuery):
    _, sid, mid = c.data.split(":")
    if sid not in SERVICES:
        return await c.answer()
    await show_days(c, sid, mid)


async def show_days(c: CallbackQuery, sid: str, mid: str):
    ds = [(day, label) for day, label in days() if slots(day, sid, mid)]
    if not ds:
        await c.message.answer("На ближайшие дни свободного времени нет 😔 Позвоните нам: " + CFG["phone"])
        return await c.answer()
    rows = [[btn(label, f"d:{sid}:{mid}:{day}") for day, label in ds[i:i + 3]] for i in range(0, len(ds), 3)]
    await c.message.edit_text("Выберите день:", reply_markup=kb(*rows, [btn("← Назад", f"s:{sid}")]))
    await c.answer()


@router.callback_query(F.data.startswith("d:"))
async def pick_day(c: CallbackQuery):
    _, sid, mid, day = c.data.split(":")
    if sid not in SERVICES:
        return await c.answer()
    free = slots(day, sid, mid)
    if not free:
        return await c.answer("На этот день всё занято, выберите другой", show_alert=True)
    times = [btn(datetime.fromtimestamp(t, TZ).strftime("%H:%M"), f"t:{sid}:{mid}:{day}:{datetime.fromtimestamp(t, TZ):%H%M}")
             for t in free]
    rows = [times[i:i + 4] for i in range(0, len(times), 4)]
    await c.message.edit_text("Выберите время:", reply_markup=kb(*rows, [btn("← Другой день", f"m:{sid}:{mid}")]))
    await c.answer()


@router.callback_query(F.data.startswith("t:"))
async def pick_time(c: CallbackQuery):
    _, sid, mid, day, hm = c.data.split(":")
    if sid not in SERVICES:
        return await c.answer()
    start = int(datetime.strptime(day + hm, "%y%m%d%H%M").replace(tzinfo=TZ).timestamp())
    if start not in slots(day, sid, mid):
        return await c.answer("Это время только что заняли, выберите другое", show_alert=True)
    uid = c.from_user.id
    store.touch_client(uid, c.from_user.first_name or "")
    PENDING[uid] = {"sid": sid, "mid": mid, "start": start}
    if store.phone(uid):
        await confirm_screen(c.message, uid)
    else:
        await c.message.answer("Оставьте номер телефона, чтобы мы могли связаться, если что-то изменится:",
                               reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить мой номер",
                                                                                          request_contact=True)]],
                                                                resize_keyboard=True, one_time_keyboard=True))
    await c.answer()


async def confirm_screen(m: Message, uid: int):
    p = PENDING[uid]
    who = "любой свободный мастер" if p["mid"] == "*" else master_name(p["mid"])
    s = SERVICES[p["sid"]]
    text = (f"Проверьте запись:\n\n<b>{s['name']}</b> · {s['price']}\n" + (f"Мастер: {who}\n" if MASTERS else "") +
            f"🗓 {when(p['start'])}\n📞 {store.phone(uid)}")
    await m.answer(text, parse_mode="HTML", reply_markup=kb([btn("✅ Подтвердить", "ok")], [btn("Изменить", "b:s")]))


@router.message(F.contact)
async def got_contact(m: Message):
    await save_phone(m, m.contact.phone_number)


async def save_phone(m: Message, phone: str):
    uid = m.from_user.id
    store.touch_client(uid, m.from_user.first_name or "")
    store.set_phone(uid, phone)
    await m.answer("Спасибо, номер сохранён.", reply_markup=ReplyKeyboardRemove())
    if uid in PENDING:
        await confirm_screen(m, uid)


@router.callback_query(F.data == "ok")
async def confirm(c: CallbackQuery):
    uid = c.from_user.id
    p = PENDING.pop(uid, None)
    if p is None:
        return await c.answer("Начните запись заново: /start", show_alert=True)
    s = SERVICES[p["sid"]]
    master = free_master(p["mid"], p["start"], s["minutes"])
    if master is None:
        await c.message.answer("Увы, это время уже заняли. Выберите другое:", reply_markup=kb([btn("📅 Записаться", "b:s")]))
        return await c.answer()
    name = c.from_user.first_name or ""
    bid = store.add(uid, name, store.phone(uid), p["sid"], master, p["start"], s["minutes"])
    b = store.get(bid)
    await c.message.answer(f"✅ <b>Вы записаны!</b>\n\n{describe(b)}\n📍 {CFG['address']}\n\nНапомним заранее. Если планы изменятся, "
                           "отмените запись в «Мои записи».", parse_mode="HTML", reply_markup=main_menu())
    for admin in admins():
        try:
            await c.bot.send_message(admin, f"🆕 Новая запись №{bid}\n\n{describe(b)}\n👤 {name} · {b['phone']}",
                                     reply_markup=kb([btn("❌ Отменить запись", f"ac:{bid}")]))
        except Exception:
            pass
    await c.answer()


@router.callback_query(F.data == "my")
async def my(c: CallbackQuery):
    items = store.upcoming(uid=c.from_user.id, frm=int(clock()))
    if not items:
        await c.message.answer("У вас нет предстоящих записей.", reply_markup=kb([btn("📅 Записаться", "b:s")]))
        return await c.answer()
    for b in items[:5]:
        await c.message.answer(describe(b), reply_markup=kb([btn("❌ Отменить", f"c:{b['id']}")]))
    await c.answer()


@router.callback_query(F.data.startswith("c:"))
async def client_cancel(c: CallbackQuery):
    b = store.get(int(c.data[2:])) if c.data[2:].isdigit() else None
    if b is None or b["user_id"] != c.from_user.id or not store.cancel(b["id"]):
        return await c.answer("Эта запись уже отменена", show_alert=True)
    await c.message.answer("Запись отменена. Будем рады видеть вас в другой раз!", reply_markup=main_menu())
    for admin in admins():
        try:
            await c.bot.send_message(admin, f"↩️ Клиент отменил запись №{b['id']}\n\n{describe(b)}\n👤 {b['name']} · {b['phone']}")
        except Exception:
            pass
    await c.answer()


@router.callback_query(F.data.startswith("rm:"))
async def will_come(c: CallbackQuery):
    await c.answer("Спасибо, ждём вас!", show_alert=True)


# ---- admin ------------------------------------------------------------------------------------
@router.callback_query(F.data.startswith("ac:"))
async def admin_cancel(c: CallbackQuery):
    if c.from_user.id not in admins():
        return await c.answer()
    b = store.get(int(c.data[3:])) if c.data[3:].isdigit() else None
    if b is None or not store.cancel(b["id"]):
        return await c.answer("Уже отменена", show_alert=True)
    await c.message.answer(f"Запись №{b['id']} отменена, клиент получил сообщение.")
    try:
        await c.bot.send_message(b["user_id"], f"😔 К сожалению, ваша запись отменена:\n\n{describe(b)}\n\n"
                                               f"Выберите другое время или позвоните: {CFG['phone']}",
                                 reply_markup=kb([btn("📅 Записаться снова", "b:s")]))
    except Exception:
        pass
    await c.answer()


def day_bounds(offset: int):
    d = datetime.fromtimestamp(clock(), TZ).date() + timedelta(days=offset)
    start = datetime.combine(d, datetime.min.time(), TZ).timestamp()
    return int(start), int(start + 86400)


async def schedule(m: Message, frm: int, to: int, title: str):
    if m.from_user.id not in admins():
        return
    items = store.upcoming(frm=frm, to=to)
    if not items:
        return await m.answer(f"{title}: записей нет.")
    lines = [f"{datetime.fromtimestamp(b['start'], TZ):%d.%m %H:%M} · {service_name(b['service'])}"
             + (f" · {master_name(b['master'])}" if b["master"] else "") + f"\n   👤 {b['name']} · {b['phone']} (№{b['id']})"
             for b in items]
    await m.answer(f"{title}:\n\n" + "\n".join(lines))


@router.message(Command("today"))
async def today_cmd(m: Message):
    await schedule(m, int(clock()) - 3600, day_bounds(0)[1], "Сегодня")


@router.message(Command("tomorrow"))
async def tomorrow_cmd(m: Message):
    await schedule(m, *day_bounds(1), "Завтра")


@router.message(Command("week"))
async def week_cmd(m: Message):
    await schedule(m, day_bounds(0)[0], day_bounds(7)[0], "Неделя")


ADMIN_HELP = ("Команды администратора:\n"
              "/today, /tomorrow, /week: расписание\n"
              "/off 30.10: закрыть день (праздник, отпуск)\n"
              "/on 30.10: открыть день обратно\n"
              "/block 30.10 15:00-16:30 [мастер]: занять время (запись по телефону, перерыв)\n"
              "/stats: цифры за неделю")


def parse_day(text: str):
    """'30.10' or '30.10.2026' -> 'yymmdd' (the nearest such date from today on), or None."""
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?", text.strip())
    if not m:
        return None
    today = datetime.fromtimestamp(clock(), TZ).date()
    year = int(m.group(3)) if m.group(3) else today.year
    try:
        d = datetime(year, int(m.group(2)), int(m.group(1))).date()
    except ValueError:
        return None
    if not m.group(3) and d < today:
        d = d.replace(year=d.year + 1)
    return d.strftime("%y%m%d")


def args_of(m: Message) -> str:
    parts = (m.text or "").split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


@router.message(Command("admin"))
async def admin_help(m: Message):
    if m.from_user.id in admins():
        await m.answer(ADMIN_HELP)


@router.message(Command("off", "on"))
async def toggle_day(m: Message):
    if m.from_user.id not in admins():
        return
    day = parse_day(args_of(m))
    if day is None:
        return await m.answer("Укажите дату, например: /off 30.10")
    closing = (m.text or "").startswith("/off")
    store.set_closed(day, closing)
    label = datetime.strptime(day, "%y%m%d").strftime("%d.%m.%Y")
    if closing:
        clash = store.upcoming(frm=int(datetime.strptime(day, "%y%m%d").replace(tzinfo=TZ).timestamp()),
                               to=int(datetime.strptime(day, "%y%m%d").replace(tzinfo=TZ).timestamp()) + 86400)
        note = f"\n⚠️ На этот день уже есть записи ({len(clash)}), их нужно перенести: /today или /week." if clash else ""
        await m.answer(f"🔒 {label}: день закрыт для записи.{note}")
    else:
        await m.answer(f"🔓 {label}: день снова открыт для записи.")


@router.message(Command("block"))
async def block(m: Message):
    if m.from_user.id not in admins():
        return
    parts = args_of(m).split()
    rng = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", parts[1]) if len(parts) >= 2 else None
    day = parse_day(parts[0]) if parts else None
    if day is None or rng is None:
        return await m.answer("Пример: /block 30.10 15:00-16:30 Арман  (мастера можно не указывать, тогда занято у всех)")
    h1, m1, h2, m2 = map(int, rng.groups())
    base = datetime.strptime(day, "%y%m%d").replace(tzinfo=TZ)
    start, end = int((base + timedelta(hours=h1, minutes=m1)).timestamp()), int((base + timedelta(hours=h2, minutes=m2)).timestamp())
    if end <= start:
        return await m.answer("Конец должен быть позже начала.")
    who = " ".join(parts[2:]).strip().lower()
    targets = [mid for mid, x in MASTERS.items() if not who or x["name"].lower() == who] if MASTERS else [""]
    if MASTERS and who and not targets:
        return await m.answer("Нет такого мастера. Мастера: " + ", ".join(x["name"] for x in MASTERS.values()))
    for mid in targets:
        store.add(0, "Занято (администратор)", "", "block", mid, start, (end - start) // 60)
    names = ", ".join(master_name(t) for t in targets if t) or "всех"
    await m.answer(f"⛔ {base:%d.%m} {h1:02d}:{m1:02d}–{h2:02d}:{m2:02d} занято у: {names}.")


@router.message(Command("stats"))
async def stats_cmd(m: Message):
    if m.from_user.id not in admins():
        return
    s = store.stats(int(clock()))
    await m.answer(f"👥 Клиентов: {s['clients']}\n📅 Записей за 7 дней: {s['bookings_week']} (отмен: {s['cancelled_week']})\n"
                   f"⏳ Предстоящих: {s['upcoming']}")


@router.message(F.text)
async def text(m: Message):
    t = (m.text or "").strip()
    if m.from_user.id in PENDING and PHONE.match(t):
        return await save_phone(m, t)
    if t.startswith("/"):
        return
    await m.answer("Я помогу записаться 🙂 Выберите действие:", reply_markup=main_menu())


@router.callback_query()
async def stale(c: CallbackQuery):
    await c.answer("Кнопка устарела, нажмите /start", show_alert=True)


async def send_reminders(bot) -> int:
    """Called every minute: reminds clients about bookings starting soon. Returns how many were sent."""
    sent = 0
    for b in store.due_reminders(int(clock()), CFG.get("remind_minutes", 120)):
        store.mark_reminded(b["id"])
        try:
            await bot.send_message(b["user_id"], f"⏰ Напоминаем о записи:\n\n{describe(b)}\n📍 {CFG['address']}",
                                   reply_markup=kb([btn("✅ Приду", f"rm:{b['id']}"), btn("❌ Отменить", f"c:{b['id']}")]))
            sent += 1
        except Exception:
            pass
    return sent
