"""The digest bot's side of the conversation: it answers /start and lets people get the digest in a DM."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from common.config import env, lang_of
from common.db import Store

store = Store("digest")
router = Router()

T = {
    "ru": {
        "welcome": ("<b>Гик-дайджест</b>: главное из мира ИИ, игр, техники и науки одним выпуском в день.\n\n"
                    "Каждое утро в 9:00 по Алматы: обложка и по 3 новости из каждой рубрики со ссылками. Без воды.\n\n"
                    "Читай в канале или получай выпуск прямо сюда, в личку."),
        "channel": "📰 Открыть канал", "sub_on": "🔔 Получать в личку", "sub_off": "🔕 Отключить рассылку",
        "lang": "🌐 English edition", "subbed": "🔔 Готово, выпуск будет приходить сюда каждое утро.",
        "unsubbed": "🔕 Рассылка отключена.", "stale": "Эта кнопка устарела. Нажми /start.",
        "more": "Ещё от нас:",
    },
    "en": {
        "welcome": ("<b>Geek Digest</b>: the day's best of AI, games, tech and science in one post.\n\n"
                    "Every morning at 9:00 (Almaty time): a cover and 3 stories per section with links. No fluff.\n\n"
                    "Read it in the channel or get each issue right here in the chat."),
        "channel": "📰 Open the channel", "sub_on": "🔔 Send it to me here", "sub_off": "🔕 Stop sending",
        "lang": "🌐 Русская версия", "subbed": "🔔 Done, the issue will arrive here every morning.",
        "unsubbed": "🔕 Delivery turned off.", "stale": "This button is outdated. Press /start.",
        "more": "More from us:",
    },
}


def lang(user) -> str:
    return store.get_lang(user.id) or lang_of(user)


def channel_url(lg: str) -> str:
    handle = (env("CHANNEL_EN") if lg == "en" else "") or env("CHANNEL") or "@geekdigests"
    return f"https://t.me/{handle.lstrip('@')}"


def menu(user) -> InlineKeyboardMarkup:
    lg = lang(user)
    t = T[lg]
    on = store.is_sub(user.id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["channel"], url=channel_url(lg))],
        [InlineKeyboardButton(text=t["sub_off"] if on else t["sub_on"], callback_data="sub")],
        [InlineKeyboardButton(text=t["lang"], callback_data="lang")],
        [InlineKeyboardButton(text="🧠 Wordlore", url="https://t.me/wordlore_bot"),
         InlineKeyboardButton(text="🎲 IdeaForge", url="https://t.me/ideaforge_gen_bot")],
    ])


@router.message(CommandStart())
@router.message(Command("help"))
async def start(m: Message):
    user = m.from_user
    store.ensure_user(user.id)
    if not store.get_lang(user.id):
        store.set_lang(user.id, lang_of(user))
    await m.answer(T[lang(user)]["welcome"], parse_mode="HTML", reply_markup=menu(user))


@router.message(Command("sub"))
async def sub_cmd(m: Message):
    user = m.from_user
    store.ensure_user(user.id)
    on = not store.is_sub(user.id)
    store.set_sub(user.id, on)
    await m.answer(T[lang(user)]["subbed" if on else "unsubbed"], reply_markup=menu(user))


@router.message(Command("stats"))
async def stats_cmd(m: Message):
    if str(m.from_user.id) != env("OWNER_ID"):
        return
    subs = store.subs()
    ru = sum(1 for u in subs if (store.get_lang(u) or "ru") == "ru")
    await m.answer(f"{store.stats_text()}\n\n🇷🇺 в личке: {ru}\n🇬🇧 в личке: {len(subs) - ru}")


@router.callback_query(F.data == "sub")
async def toggle_sub(c: CallbackQuery):
    user = c.from_user
    store.ensure_user(user.id)
    on = not store.is_sub(user.id)
    store.set_sub(user.id, on)
    await c.message.answer(T[lang(user)]["subbed" if on else "unsubbed"], reply_markup=menu(user))
    await c.answer()


@router.callback_query(F.data == "lang")
async def toggle_lang(c: CallbackQuery):
    user = c.from_user
    store.ensure_user(user.id)
    store.set_lang(user.id, "en" if lang(user) == "ru" else "ru")
    await c.message.answer(T[lang(user)]["welcome"], parse_mode="HTML", reply_markup=menu(user))
    await c.answer()


@router.message(Command("lang"))
async def lang_cmd(m: Message):
    user = m.from_user
    store.ensure_user(user.id)
    store.set_lang(user.id, "en" if lang(user) == "ru" else "ru")
    await m.answer(T[lang(user)]["welcome"], parse_mode="HTML", reply_markup=menu(user))


@router.callback_query()
async def stale(c: CallbackQuery):
    await c.answer(T[lang(c.from_user)]["stale"], show_alert=True)
