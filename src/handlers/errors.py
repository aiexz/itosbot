from aiogram import Router, F, Bot
from aiogram.types import Message, ErrorEvent

router = Router()


@router.error()
async def start(event: ErrorEvent, bot: Bot):
    await event.update.message.answer(
        "The bot can't process it. Please tell me what you were trying to do.\n"
        "Message here -> @aiexz"
    )
    raise event.exception
