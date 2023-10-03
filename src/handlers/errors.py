from aiogram import Router, F, Bot
from aiogram.types import Message, ErrorEvent

router = Router()


@router.error()
async def start(event: ErrorEvent, bot: Bot):
    await event.update.message.answer(
        "Congrats, you broke the bot. Now go ahead and submit an issue.\n"
        "https://github.com/aiexz/itosbot/issues/new"
    )
    raise event.exception
