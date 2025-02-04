import logging
from aiogram import Router, Bot
from aiogram.types import ErrorEvent
from aiogram.exceptions import TelegramNetworkError

router = Router()


@router.error()
async def start(event: ErrorEvent, bot: Bot):
    if isinstance(event.exception, TelegramNetworkError):
        return
    
    await event.update.message.answer(
        "The bot can't process it. Please tell me what you were trying to do.\n"
        "Message here -> @aiexz"
    )

    raise event.exception
