"""Runs the digest bot: answers /start and posts the digest every day at DIGEST_TIME (Kazakhstan time)."""
import asyncio
import logging

from aiogram import Bot, Dispatcher

from common.config import env
from common.daily import every_day
from common.profile import setup_profile
from digest.bot import router, store
from digest.digest import main as post_digest
from digest.profile import COMMANDS, DESCRIPTION, SHORT


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(env("BOT_TOKEN"))
    dp = Dispatcher()
    dp.include_router(router)
    await setup_profile(bot, COMMANDS, DESCRIPTION, SHORT)
    await asyncio.gather(
        dp.start_polling(bot),
        every_day(env("DIGEST_TIME", "09:00"), lambda: post_digest(store=store)),
    )


if __name__ == "__main__":
    asyncio.run(main())
