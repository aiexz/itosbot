'''AntiFloodMiddleware module handles flood control by limiting high-frequency message events.'''

import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message


class AntiFloodMiddleware(BaseMiddleware):
    """Middleware to prevent message flooding by enforcing a cooldown period per user."""
    def __init__(self) -> None:
        self.flood_cache: Dict[int, datetime] = {}

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any],
    ) -> Any:
        """Intercepts messages flagged as 'new_stickers' and limits processing if within cooldown period.

        Args:
            handler: The next middleware or handler in the chain.
            event: The incoming Message object.
            data: Additional data passed along the call chain.

        Returns:
            The result from the handler if not throttled, otherwise None.
        """
        if get_flag(data, "new_stickers"):
            user_id = event.from_user.id
            now = datetime.now()
            if user_id in self.flood_cache and self.flood_cache[user_id] > now:
                logging.info("User %s is sending messages too frequently; ignoring.", user_id)
                return
            else:
                self.flood_cache.pop(user_id, None)
            try:
                return await handler(event, data)
            except TelegramRetryAfter as e:
                self.flood_cache[user_id] = now + timedelta(seconds=e.retry_after)
                logging.info("Too many requests from %s. Try again in %s seconds.", user_id, e.retry_after)
                return
        else:
            return await handler(event, data)

