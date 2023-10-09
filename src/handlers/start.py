from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()


@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Hey, send me photo, video or GIF and I'll convert it to a sticker pack.\nCheck guide for more info",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📖 How to use",
                        url="https://telegra.ph/Guide-to-itosbot-05-05",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Result video",
                        url="https://t.me/addemoji/video_443446876_AzP5m_by_itosbot",
                    ),
                    InlineKeyboardButton(
                        text="Photo",
                        url="https://t.me/addstickers/emojis_443446876_UZN6c_by_itosbot",
                    )
                ],
            ]
        ),
    )
