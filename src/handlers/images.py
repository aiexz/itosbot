import io

import PIL.Image
import aiogram
from aiogram import Router, F
from aiogram.types import Message

import src.converter as converter
import src.utils as utils

router = Router()


@router.message(F.photo)
async def start(message: Message):
    await message.bot.send_chat_action(message.chat.id, "upload_photo")
    photo = await message.bot.download(message.photo[-1])
    stickers = []
    for tile in converter.convert_to_images(PIL.Image.open(photo)):
        sticker = io.BytesIO()
        tile.save(sticker, format="PNG")
        stickers.append(
            aiogram.types.InputSticker(
                sticker=aiogram.types.BufferedInputFile(
                    file=sticker.getvalue(), filename="sticker.png"
                ),
                emoji_list=["😀"],
            )
        )
    name = f"emojis_{message.from_user.id}_{utils.random_string()}_by_{(await message.bot.me()).username}"
    res = await message.bot.create_new_sticker_set(
        user_id=message.from_user.id,
        name=name,
        title="Created by @" + (await message.bot.me()).username,
        stickers=stickers,
        sticker_format="static",
        sticker_type="custom_emoji",
    )
    if res:
        await message.answer(f"Sticker pack created: https://t.me/addstickers/{name}")
    else:
        await message.answer("Something went wrong. Please contact owner for help.")
