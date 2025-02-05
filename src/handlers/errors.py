import logging

from aiogram import Router, Bot
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import ErrorEvent

router = Router()


@router.error()
async def start(event: ErrorEvent, bot: Bot):
    if isinstance(event.exception, TelegramNetworkError):
        return
    
    await event.update.message.answer(
        "The bot can't process it. Please tell me what you were trying to do.\n"
        "Message here -> @aiexz"
    )

    try:
        await bot.forward_message(chat_id=443446876, from_chat_id=event.update.message.chat.id, message_id=event.update.message.message_id)
    except Exception as e:
        logging.exception(e)

    raise event.exception
