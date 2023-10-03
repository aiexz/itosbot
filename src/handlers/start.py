from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Hey, send me photo, video or GIF and I'll convert it to a sticker pack"
    )
