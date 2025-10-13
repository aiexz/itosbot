import logging
import tempfile

import aiogram.types.input_file
from aiogram import Router, F
from aiogram.types import Message

import src.converter.video as converter
from src import utils

router = Router()


@router.message(F.animation | F.video, flags={"new_stickers": True})
@router.message(F.document.mime_type.in_(["image/gif","video/mp4", "video/webm"]), flags={"new_stickers": True})
async def video_converter(message: Message):
    await message.bot.send_chat_action(message.chat.id, "upload_video")
    message_text = message.caption
    
    custom_width, bg_color, b_sim, b_blend = 0, None, 30, 0
    title = "Created by @" + (await message.bot.me()).username
    # Parse command arguments if present
    if message_text and message_text.startswith("/convert"):
        command_args = message_text.removeprefix("/convert").strip().split()
        command_map = {k: v for k, v in (arg.split("=") for arg in command_args if "=" in arg)}
        try:
            custom_width = int(command_map.get("w", 0))
            custom_width = max(0, custom_width)  # width can't be negative
            custom_width = custom_width * 100  # convert to pixels
        except ValueError:
            custom_width = 0
        bg_color = command_map.get("b", None) # background color
        try:
            b_sim = float(command_map.get("b_sim", "20"))
            b_sim = max(0, min(100, b_sim)) # clamp to 0-100
        except ValueError:
            b_sim = 20
        try:
            b_blend = float(command_map.get("b_blend", "0"))
            b_blend = max(0, min(100, b_blend)) # clamp to 0-100
        except ValueError:
            b_blend = 0
        title_map = command_map.get("name", None) # name for our pack
        if title_map is not None:
            # 64 - w/ @itosbot
            title = title_map[:50] + " w/ @" + (await message.bot.me()).username

    
    if message.animation:
        if message.animation.duration > 5:
            await message.answer(
                "Sorry, but I can't convert animations longer than 5 seconds."
            )
            return
        video = await message.bot.download(message.animation.file_id)
    elif message.document:
        video = await message.bot.download(message.document.file_id)
        with tempfile.NamedTemporaryFile() as f:
            f.write(video.read())
            f.flush()
            video.seek(0)
            length = await converter.get_video_length(f.name)
            if length > 5:
                await message.answer(
                    "Sorry, but I can't convert videos longer than 5 seconds."
                )
                return
    else:
        if message.video.duration > 5:
            await message.answer(
                "Sorry, but I can't convert videos longer than 5 seconds."
            )
            return
        video = await message.bot.download(message.video.file_id)

    try:
        result = await converter.convert_video(video, custom_width, bg_color, b_sim, b_blend)
    except converter.ConversionError as e:
        await message.answer("Sorry, but I can't convert this video. It is probably too long.\n" + str(e))
        return
    except Exception as e:
        await message.answer("Some unexpected error occurred, sorry")
        logging.exception(e)
        return
    if len(result) > 50:
        logging.error("Too many tiles", len(result))
    stickers = []
    for tile in result:
        stickers.append(
            aiogram.types.InputSticker(
                sticker=aiogram.types.input_file.FSInputFile(
                    path=tile, filename="sticker.webm"
                ),
                emoji_list=["😀"],
                format="video",
            )
        )
    name = f"video_{message.from_user.id}_{utils.random_string()}_by_{(await message.bot.me()).username}"
    try:
        res = await message.bot.create_new_sticker_set(
            user_id=message.from_user.id,
            name=name,
            title=title,
            stickers=stickers,
            sticker_format="video",
            needs_repainting=False,
            sticker_type="custom_emoji",
        )
    except Exception as e:
        raise e

    if res:
        await message.answer(f"Sticker pack created: https://t.me/addemoji/{name}")
        logging.info(f"Sticker pack created: https://t.me/addemoji/{name}")
    else:
        await message.answer("Something went wrong. Please contact @aiexzbot for help.")
