import os

import aiogram.types.input_file
from aiogram import Router, F
from aiogram.types import Message
import src.converter.video as converter
from src import utils

router = Router()


@router.message(F.animation | F.video)
async def start(message: Message):
    await message.bot.send_chat_action(message.chat.id, "upload_video")
    if message.animation:
        if message.animation.duration > 3:
            await message.answer(
                "Sorry, but I can't convert animations longer than 3 seconds."
            )
            return
        video = await message.bot.download(message.animation.file_id)
    else:
        if message.video.duration > 3:
            await message.answer(
                "Sorry, but I can't convert videos longer than 3 seconds."
            )
            return
        video = await message.bot.download(message.video.file_id)

    try:
        result = converter.convert_video(video)
    except converter.ConversionError as e:
        await message.answer("Sorry, but I can't convert this video.\n" + str(e))
        return
    stickers = []
    for tile in result:
        stickers.append(
            aiogram.types.InputSticker(
                sticker=aiogram.types.input_file.FSInputFile(
                    path=tile, filename="sticker.webm"
                ),
                emoji_list=["😀"],
            )
        )
    name = f"emojis_{message.from_user.id}_{utils.random_string()}_by_{(await message.bot.me()).username}"
    try:
        res = await message.bot.create_new_sticker_set(
            user_id=message.from_user.id,
            name=name,
            title="Created by @" + (await message.bot.me()).username,
            stickers=stickers,
            sticker_format="video",
            needs_repainting=True,
            sticker_type="custom_emoji",
        )
    except Exception as e:
        raise e

    if res:
        await message.answer(f"Sticker pack created: https://t.me/addstickers/{name}")
    else:
        await message.answer("Something went wrong. Please contact owner for help.")
