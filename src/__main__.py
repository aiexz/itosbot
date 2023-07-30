import asyncio
import logging

import aiogram.client.telegram
import aiogram.fsm.storage.memory
from aiogram import Bot, Dispatcher

from src.handlers import setup_routers
from src.settings import Settings

settings = Settings()


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    storage = aiogram.fsm.storage.memory.MemoryStorage()
    dp = Dispatcher(storage=storage)

    router = setup_routers()
    dp.include_router(router)

    await dp.start_polling(
        bot, allowed_updates=dp.resolve_used_update_types(), skip_updates=True
    )


if __name__ == "__main__":
    asyncio.run(main())
