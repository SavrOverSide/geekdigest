"""Bot profile shown inside Telegram: the command menu, the intro text on the empty chat screen
(the one with the START button) and the short line in search results. Set on every start, so editing
the texts and redeploying is enough."""
import logging

from aiogram.types import BotCommand

LIMITS = {"description": 512, "short": 120}


async def setup_profile(bot, commands: dict, description: dict, short: dict) -> None:
    """Each argument is {language: ...}; 'en' is also the default for every other language."""
    for lg in description:
        for text, kind in ((description[lg], "description"), (short[lg], "short")):
            assert len(text) <= LIMITS[kind], (lg, kind, len(text))
        code = None if lg == "en" else lg
        try:
            await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in commands[lg]], language_code=code)
            await bot.set_my_description(description[lg], language_code=code)
            await bot.set_my_short_description(short[lg], language_code=code)
            if lg == "en":  # also the default for everyone else; explicit 'en' covers English clients
                await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in commands[lg]], language_code="en")
                await bot.set_my_description(description[lg], language_code="en")
                await bot.set_my_short_description(short[lg], language_code="en")
        except Exception:  # cosmetic: never stop the bot because of it
            logging.exception("profile setup failed for %s", lg)
