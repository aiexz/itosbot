import io
import logging

import PIL.Image
import aiogram
from aiogram import Router, F
from aiogram.types import Message

import src.converter as converter
import src.utils as utils

router = Router()


@router.message(F.photo, flags={"new_stickers": True})
@router.message(F.document.mime_type.in_(["image/png", "image/jpeg", "image/webp"]), flags={"new_stickers": True})
async def image_converter(message: Message):
    await message.bot.send_chat_action(message.chat.id, "upload_photo")
    max_size_bytes = 20 * 1024 * 1024 # 20MB
    if message.photo:
        message_text = message.caption
        if message.photo[-1].file_size and message.photo[-1].file_size > max_size_bytes:
            await message.answer("Sorry, we cannot process files bigger than 20MB.")
            return
        photo = await message.bot.download(message.photo[-1])
    elif message.document:
        message_text = message.caption
        if message.document.file_size and message.document.file_size > max_size_bytes:
            await message.answer("Sorry, we cannot process files bigger than 20MB.")
            return
        photo = await message.bot.download(message.document.file_id)
    else:
        raise ValueError("No photo or document provided")
    custom_width, custom_height, bg_color, b_sim, b_blend = 0, 0, None, 30, 0
    title = "Created by @" + (await message.bot.me()).username
    # Parse command arguments if present
    if message_text and message_text.startswith("/convert"):
        # shoutout to @drip_tech for this style
        command_args = message_text.removeprefix("/convert").strip().split()
        command_map = {
            k: v for k, v in (arg.split("=", 1) for arg in command_args if "=" in arg)
        }
        try:
            custom_width = int(command_map.get("w", 0))
            custom_width = max(0, custom_width) # width can't be negative
            custom_width = custom_width * 100 # convert to pixels
        except ValueError:
            custom_width = 0
        try:
            custom_height = int(command_map.get("h", 0))
            custom_height = max(0, custom_height) # height can't be negative
            custom_height = custom_height * 100 # convert to pixels
        except ValueError:
            custom_height = 0
        bg_color = command_map.get("b", None) # background color
        try:
            b_sim = float(command_map.get("b_sim", "30"))
            b_sim = max(0, min(100, b_sim)) # clamp to 0-100
        except ValueError:
            b_sim = 30
        try:
            b_blend = float(command_map.get("b_blend", "0"))
            b_blend = max(0, min(100, b_blend)) # clamp to 0-100
        except ValueError:
            b_blend = 0
        title_map = command_map.get("name", None) # name for our pack
        if title_map:
            # 64 - w/ @itosbot
            title = title_map[:50] + " w/ @" + (await message.bot.me()).username


    stickers = []
    try:
        tiles, tiles_width, tiles_height = converter.convert_to_images(
            PIL.Image.open(photo),
            custom_width,
            custom_height,
            bg_color,
            b_sim,
            b_blend,
        )
    except converter.TileLimitError as e:
        await message.answer(f"❌ {str(e)}")
        return
    except converter.DimensionError as e:
        await message.answer(f"❌ {str(e)}")
        return
    except ValueError as e:
        await message.answer(f"❌ Invalid image: {str(e)}")
        return
    
    for tile in tiles:
        sticker = io.BytesIO()
        tile.save(sticker, format="PNG")
        stickers.append(
            aiogram.types.InputSticker(
                sticker=aiogram.types.BufferedInputFile(
                    file=sticker.getvalue(), filename="sticker.png"
                ),
                emoji_list=["😀"],
                format="static",
            )
        )
    name = f"emojis_{message.from_user.id}_{utils.random_string()}_by_{(await message.bot.me()).username}"
    try:
        res = await message.bot.create_new_sticker_set(
            user_id=message.from_user.id,
            name=name,
            title=title,
            stickers=stickers,
            sticker_format="static",
            sticker_type="custom_emoji",
        )
    except Exception as e:
        logging.exception(e)
        await message.answer("Failed to create sticker set. Please try again later.")
        return
    if res:
        try:
            sticker_set = await message.bot.get_sticker_set(name=name)
            msg_parts = []
            for index, sticker in enumerate(sticker_set.stickers):
                msg_parts.append(f"<tg-emoji emoji-id=\"{sticker.custom_emoji_id}\">🤯</tg-emoji>")
                if (index + 1) % tiles_width == 0:
                    msg_parts.append("\n")
            msg = "".join(msg_parts).strip()
            await message.answer(msg, parse_mode="HTML")
        except Exception as e:
            logging.exception(e)
            await message.answer(f"Sticker pack created: https://t.me/addemoji/{name}")
            await message.bot.send_message(
                chat_id=443446876,
                text=f"Custom emoji send failed for {name}: {type(e).__name__}: {e}",
            )
        logging.info(f"Sticker pack created: https://t.me/addemoji/{name}")
    else:
        await message.answer("Something went wrong. Please contact owner for help.")
