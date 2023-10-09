import asyncio
import logging

import aiogram.client.telegram
import aiogram.fsm.storage.memory
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from src.handlers import setup_routers
from src.middlewares import AntiFloodMiddleware
from src.settings import Settings

settings = Settings()


async def main():
    logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    try:
        async with aiohttp.ClientSession() as session:
            await session.get("http://nginx")
        bot_session = AiohttpSession(
                api=TelegramAPIServer.from_base('http://nginx')
        )
    except aiohttp.ClientConnectorError:
        logging.warning("Can't connect to local bot api, using default server")
        bot_session = AiohttpSession()

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), session=bot_session)
    storage = aiogram.fsm.storage.memory.MemoryStorage()
    dp = Dispatcher(storage=storage)

    router = setup_routers()
    dp.include_router(router)
    dp.message.middleware(AntiFloodMiddleware())

    await dp.start_polling(
        bot, allowed_updates=dp.resolve_used_update_types(), skip_updates=True
    )


if __name__ == "__main__":
    asyncio.run(main())
