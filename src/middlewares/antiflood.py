"""AntiFloodMiddleware module handles flood control by limiting high-frequency message events."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message

from src.sticker_rate_limit import (
    format_retry_message,
    get_retry_until,
    save_retry_after,
)


class AntiFloodMiddleware(BaseMiddleware):
    """Middleware to prevent message flooding by enforcing a cooldown period per user."""

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
            if event.from_user is None:
                return await handler(event, data)

            user_id = event.from_user.id
            retry_until = get_retry_until(user_id)
            if retry_until is not None:
                logging.info(
                    "User %s is blocked from sticker creation until %s.",
                    user_id,
                    retry_until.isoformat(),
                )
                await event.answer(format_retry_message(retry_until))
                return
            try:
                return await handler(event, data)
            except TelegramRetryAfter as e:
                retry_until = save_retry_after(user_id, e.retry_after)
                logging.info(
                    "Too many requests from %s. Try again after %s.",
                    user_id,
                    retry_until.isoformat(),
                )
                await event.answer(format_retry_message(retry_until))
                return
        else:
            return await handler(event, data)
