import logging
import os
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY")

if not BOT_TOKEN or not SECRET_KEY:
    logger.error("BOT_TOKEN and SECRET_KEY must be set in environment")
    raise SystemExit(1)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
scheduler = AsyncIOScheduler(timezone="UTC")
