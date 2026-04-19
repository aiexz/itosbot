import logging
import os
import tempfile

import aiogram.types.input_file
from aiogram import Router, F
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message

import src.converter.video as converter
from src import utils
from src.sticker_rate_limit import format_retry_message, save_retry_after

router = Router()


def _cleanup_temp_tiles(tile_paths: list[str]) -> None:
    if not tile_paths:
        return
    temp_dir = os.path.dirname(tile_paths[0])
    for path in tile_paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
        except OSError:
            logging.exception("Failed to remove temporary tile file %s", path)
    try:
        os.rmdir(temp_dir)
    except OSError:
        logging.debug("Temporary directory %s was not empty or already removed", temp_dir)


@router.message(F.animation | F.video, flags={"new_stickers": True})
@router.message(F.document.mime_type.in_(["image/gif","video/mp4", "video/webm"]), flags={"new_stickers": True})
async def video_converter(message: Message):
    await message.bot.send_chat_action(message.chat.id, "upload_video")
    message_text = message.caption
    max_size_bytes = 20 * 1024 * 1024
    
    custom_width, custom_height, bg_color, b_sim, b_blend = 0, 0, None, 30, 0
    title = "Created by @" + (await message.bot.me()).username
    # Parse command arguments if present
    if message_text and message_text.startswith("/convert"):
        command_args = message_text.removeprefix("/convert").strip().split()
        command_map = {
            k: v for k, v in (arg.split("=", 1) for arg in command_args if "=" in arg)
        }
        try:
            custom_width = int(command_map.get("w", 0))
            custom_width = max(0, custom_width)  # width can't be negative
            custom_width = custom_width * 100  # convert to pixels
        except ValueError:
            custom_width = 0
        try:
            custom_height = int(command_map.get("h", 0))
            custom_height = max(0, custom_height)  # height can't be negative
            custom_height = custom_height * 100  # convert to pixels
        except ValueError:
            custom_height = 0
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
        if message.animation.file_size and message.animation.file_size > max_size_bytes:
            await message.answer("Sorry, we cannot process files bigger than 20MB.")
            return
        if message.animation.duration > 5:
            await message.answer(
                "Sorry, but I can't convert animations longer than 5 seconds."
            )
            return
        video = await message.bot.download(message.animation.file_id)
    elif message.document:
        if message.document.file_size and message.document.file_size > max_size_bytes:
            await message.answer("Sorry, we cannot process files bigger than 20MB.")
            return
        video = await message.bot.download(message.document.file_id)
        with tempfile.NamedTemporaryFile() as f:
            f.write(video.read())
            f.flush()
            video.seek(0)
            try:
                length = await converter.get_video_length(f.name)
            except Exception as e:
                logging.exception(e)
                await message.answer("Sorry, this file format is not supported.")
                return
            if length > 5:
                await message.answer(
                    "Sorry, but I can't convert videos longer than 5 seconds."
                )
                return
    else:
        if message.video.file_size and message.video.file_size > max_size_bytes:
            await message.answer("Sorry, we cannot process files bigger than 20MB.")
            return
        if message.video.duration > 5:
            await message.answer(
                "Sorry, but I can't convert videos longer than 5 seconds."
            )
            return
        video = await message.bot.download(message.video.file_id)

    result: list[str] = []
    try:
        try:
            result, tiles_width, tiles_height = await converter.convert_video(
                video,
                custom_width,
                custom_height,
                bg_color,
                b_sim,
                b_blend,
            )
        except converter.TileLimitError as e:
            await message.answer(f"❌ {str(e)}")
            return
        except converter.ConversionError as e:
            await message.answer("Sorry, but I can't convert this video. It is probably too long.\n" + str(e))
            return
        except Exception as e:
            await message.answer("Some unexpected error occurred, sorry")
            logging.exception(e)
            return
        if len(result) > 50:
            logging.error("Too many tiles: %s", len(result))
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
        except TelegramRetryAfter as e:
            retry_until = save_retry_after(message.from_user.id, e.retry_after)
            logging.info(
                "Sticker creation rate limited for user %s until %s.",
                message.from_user.id,
                retry_until.isoformat(),
            )
            await message.answer(format_retry_message(retry_until))
            return
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
            await message.answer("Something went wrong. Please contact @aiexzbot for help.")
    finally:
        _cleanup_temp_tiles(result)
