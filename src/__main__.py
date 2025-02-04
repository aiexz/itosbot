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


async def create_bot_session() -> AiohttpSession:
    """Creates and returns a bot session using a local Telegram API if available, falling back to the default server."""
    try:
        async with aiohttp.ClientSession() as session:
            await session.get("http://nginx")
        return AiohttpSession(api=TelegramAPIServer.from_base('http://nginx'))
    except aiohttp.ClientConnectorError as e:
        logging.warning("Can't connect to local bot api, using default server. Error: %s", e)
        return AiohttpSession()


async def main() -> None:
    logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    bot_session = await create_bot_session()

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), session=bot_session)
    storage = aiogram.fsm.storage.memory.MemoryStorage()
    dp = Dispatcher(storage=storage)

    router = setup_routers()
    dp.include_router(router)
    dp.message.middleware(AntiFloodMiddleware())

    try:
        await dp.start_polling(
            bot, allowed_updates=dp.resolve_used_update_types(), skip_updates=True
        )
    except Exception as e:
        logging.exception("Unexpected error during polling: %s", e)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down gracefully")
