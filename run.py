"""Posts the digest to CHANNEL every day at DIGEST_TIME (Kazakhstan time)."""
import asyncio
import logging

from common.config import env
from common.daily import every_day
from digest.digest import main as post_digest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(every_day(env("DIGEST_TIME", "09:00"), post_digest))
