from aiogram import Router, F
from aiogram.types import Message

router = Router()


@router.message(
    F.entities & F.entities.func(lambda x: any(x.type == "custom_emoji" for x in x))
)  # catches all messages with custom emoji
async def start(message: Message):
    await message.answer("Yeah, not implemented yet.")
