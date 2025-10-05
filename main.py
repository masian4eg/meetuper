import logging
import asyncio
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot import bot, scheduler
from handlers.start_handlers import router as start_router
from handlers.admin_handlers import router as admin_router
from models import init_db, AsyncSessionLocal
from scheduler import init_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# регистрируем роутеры
dp.include_router(start_router)
dp.include_router(admin_router)

async def on_startup():
    logger.info("🚀 Запуск бота...")
    await init_db()
    await init_scheduler(bot, scheduler)
    scheduler.start()
    logger.info("✅ Планировщик запущен")


async def on_shutdown():
    logger.info("🛑 Остановка бота...")
    scheduler.shutdown()
    await bot.session.close()
    await AsyncSessionLocal().close()


async def main():
    await on_startup()
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
