import logging

from aiogram import Router, Bot
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import ErrorEvent

router = Router()


@router.error()
async def start(event: ErrorEvent, bot: Bot):
    if isinstance(event.exception, TelegramNetworkError):
        return

    message = event.update.message
    if message:
        await message.answer(
            "The bot can't process it. Please tell me what you were trying to do.\n"
            "Message here -> @aiexz"
        )

        try:
            await bot.forward_message(
                chat_id=443446876,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
        except Exception as e:
            logging.exception(e)

    logging.error(
        "Unhandled update error: %s",
        event.exception,
        exc_info=(
            type(event.exception),
            event.exception,
            event.exception.__traceback__,
        ),
    )
