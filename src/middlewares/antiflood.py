import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self):
        self.flood_cache = {}

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any],
    ) -> Any:
        if get_flag(data, "new_stickers"):
            if event.from_user.id in self.flood_cache:
                if self.flood_cache[event.from_user.id] > datetime.now():
                    await event.answer("Too many requests. Try again later.")
                    return
                else:
                    del self.flood_cache[event.from_user.id]
            try:
                return await handler(event, data)
            except TelegramRetryAfter as e:
                self.flood_cache[event.from_user.id] = datetime.now() + timedelta(seconds=e.retry_after)
                await event.answer(f"Too many requests from you. Try again in {e.retry_after} seconds.")
                logging.info(f"Too many requests from {event.from_user.id}. Try again in {e.retry_after} seconds.")
                return
        else:
            return await handler(event, data)

