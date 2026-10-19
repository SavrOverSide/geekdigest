import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .config import env

# Kazakhstan is UTC+5 all year; override with TZ_OFFSET if needed
TZ = timezone(timedelta(hours=int(env("TZ_OFFSET", "5"))))


async def every_day(at: str, job) -> None:
    """Run `job()` every day at HH:MM local time, forever."""
    hour, minute = map(int, at.split(":"))
    while True:
        now = datetime.now(TZ)
        nxt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            await job()
        except Exception:
            logging.exception("daily job failed")
