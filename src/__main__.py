import asyncio
import logging
from typing import Any

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


def _patch_poll_data(obj: Any) -> None:
    """Recursively inject defaults for newer Telegram Bot API fields missing from local server."""
    if isinstance(obj, dict):
        if "allows_multiple_answers" in obj and "allows_revoting" not in obj:
            obj.setdefault("allows_revoting", False)
            obj.setdefault("members_only", False)
        if "voter_count" in obj and "text" in obj and "persistent_id" not in obj:
            obj.setdefault("persistent_id", "")
        for v in obj.values():
            _patch_poll_data(v)
    elif isinstance(obj, list):
        for item in obj:
            _patch_poll_data(item)


class PatchedSession(AiohttpSession):
    """AiohttpSession that patches JSON responses for local Bot API server compatibility."""

    def json_loads(self, value: str, /, **kwargs: Any) -> Any:
        data = super().json_loads(value, **kwargs)
        _patch_poll_data(data)
        return data



async def create_bot_session() -> PatchedSession:
    """Creates and returns a bot session using a local Telegram API if available, falling back to the default server."""
    try:
        async with aiohttp.ClientSession() as session:
            await session.get("http://nginx")
        return PatchedSession(api=TelegramAPIServer.from_base('http://nginx'))
    except aiohttp.ClientConnectorError as e:
        logging.warning("Can't connect to local bot api, using default server. Error: %s", e)
        return PatchedSession()


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
