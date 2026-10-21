"""Runs the booking bot and the reminder loop."""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

import bot as b


async def reminders(bot: Bot):
    while True:
        try:
            await b.send_reminders(bot)
        except Exception:
            logging.exception("reminders failed")
        await asyncio.sleep(60)


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(os.environ["BOT_TOKEN"])
    dp = Dispatcher()
    dp.include_router(b.router)
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Записаться")])
        await bot.set_my_short_description(f"{b.CFG['name']}: онлайн-запись")
    except Exception:
        logging.exception("profile")
    await asyncio.gather(dp.start_polling(bot), reminders(bot))


if __name__ == "__main__":
    asyncio.run(main())
