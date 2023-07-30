from aiogram import Router, F
from aiogram.types import Message

router = Router()


@router.message(F.animation | F.video)
async def start(message: Message):
    await message.answer("Please wait, I will do it someday.")
