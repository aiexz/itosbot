import io
import math
import os
import subprocess
import tempfile
from typing import BinaryIO
import asyncio

import PIL
from PIL.Image import Image

from src.converter.exceptions import ConversionError


async def async_check_output(cmd, stderr=None):
    if stderr == subprocess.DEVNULL:
        stderr = asyncio.subprocess.DEVNULL
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=stderr)
    out, err = await proc.communicate()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
    return out


async def convert_video(video: BinaryIO):
    tempdir = tempfile.mkdtemp()
    filename = "video.mp4"
    with open(f"{tempdir}/{filename}", "wb") as f:
        f.write(video.read())
    video_dimensions = tuple(
        map(
            int,
            (
                (await async_check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "stream=width,height",
                        "-of",
                        "csv=p=0:s=x",
                        "-i",
                        f"{tempdir}/{filename}",
                    ],
                    stderr=subprocess.DEVNULL,
                ))
                .decode("utf-8")
                .split("x")
            ),
        )
    )
    if video_dimensions[0] > 100 or video_dimensions[1] > 100:
        # simillar code as in converter/image.py
        if video_dimensions[0] > 800:
            # x264 only accepts even numbers, so adjust height to nearest even number after scaling
            scaled = video_dimensions[1] / (video_dimensions[0] / 800)
            resized = int(scaled) - (int(scaled) % 2)  # round down to nearest even number

            new_filename = "video_1.mp4"
            await async_check_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    f"{tempdir}/{filename}",
                    "-an",
                    "-vf",
                    f"scale=800:{resized}",
                    f"{tempdir}/{new_filename}",
                ],
                stderr=subprocess.DEVNULL,
            )
            filename = new_filename
            video_dimensions = tuple(
                map(
                    int,
                    (
                        (await async_check_output(
                            [
                                "ffprobe",
                                "-v",
                                "error",
                                "-show_entries",
                                "stream=width,height",
                                "-of",
                                "csv=p=0:s=x",
                                "-i",
                                f"{tempdir}/{filename}",
                            ],
                            stderr=subprocess.DEVNULL,
                        ))
                        .decode("utf-8")
                        .split("x")
                    ),
                )
            )

        if video_dimensions[1] > 5000:
            # x264 only accepts even numbers, so adjust height to nearest even number after scaling
            scaled = video_dimensions[0] / (video_dimensions[1] / 5000)
            resized = int(scaled) - (int(scaled) % 2)  # round down to nearest even number
            new_filename = "video_2.mp4"
            await async_check_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    f"{tempdir}/{filename}",
                    "-an",
                    "-vf",
                    f"scale={resized}:5000",
                    f"{tempdir}/{new_filename}",
                ],
                stderr=subprocess.DEVNULL,
            )
            filename = new_filename
            video_dimensions = tuple(
                map(
                    int,
                    (
                        (await async_check_output(
                            [
                                "ffprobe",
                                "-v",
                                "error",
                                "-show_entries",
                                "stream=width,height",
                                "-of",
                                "csv=p=0:s=x",
                                "-i",
                                f"{tempdir}/video.mp4",
                            ],
                            stderr=subprocess.DEVNULL,
                        ))
                        .decode("utf-8")
                        .split("x")
                    ),
                )
            )

        aspect_ratio = video_dimensions[0] / video_dimensions[1]
        if aspect_ratio > 1:
            new_filename = "video_3.mp4"
            max_height = 50 / math.ceil(video_dimensions[0] / 100)
            await async_check_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    f"{tempdir}/{filename}",
                    "-an",
                    "-vf",
                    f"scale={video_dimensions[0]}:{min(int(max_height) * 100, video_dimensions[1])}",
                    f"{tempdir}/{new_filename}",
                ],
                stderr=subprocess.DEVNULL,
            )
            filename = new_filename
        elif aspect_ratio == 1:
            new_filename = "video_3.mp4"
            max_size = 50 / math.ceil(video_dimensions[0] / 100)
            await async_check_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    f"{tempdir}/{filename}",
                    "-an",
                    "-vf",
                    f"scale={min(int(max_size) * 100, video_dimensions[0])}:{min(int(max_size) * 100, video_dimensions[1])}",
                    f"{tempdir}/{new_filename}",
                ],
                stderr=subprocess.DEVNULL,
            )
            filename = new_filename
        else:
            new_filename = "video_3.mp4"
            max_width = 50 / math.ceil(video_dimensions[1] / 100)
            await async_check_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    f"{tempdir}/{filename}",
                    "-an",
                    "-vf",
                    f"scale={min(int(max_width) * 100, video_dimensions[0])}:{video_dimensions[1]}",
                    f"{tempdir}/{new_filename}",
                ],
                stderr=subprocess.DEVNULL,
            )
            filename = new_filename

    if (
        math.ceil(video_dimensions[0] / 100) * math.ceil(video_dimensions[1] / 100)
        <= 50
    ):
        new_filename = "video_4.webm"
        # resize video to its best dimensions
        await async_check_output(
            [
                "ffmpeg",
                "-y",
                "-i",
                f"{tempdir}/{filename}",
                "-an",
                "-vf",
                f"scale={math.ceil(video_dimensions[0] / 100) * 100}:{math.ceil(video_dimensions[1] / 100) * 100}",
                f"{tempdir}/{new_filename}",
            ],
            stderr=subprocess.DEVNULL,
        )
        filename = new_filename

    video_dimensions = tuple(
        map(
            int,
            (
                (await async_check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "stream=width,height",
                        "-of",
                        "csv=p=0:s=x",
                        "-i",
                        f"{tempdir}/{filename}",
                    ],
                    stderr=subprocess.DEVNULL,
                ))
                .decode("utf-8")
                .split("x")
            ),
        )
    )

    usefull_tiles = []
    for i in range(math.ceil(video_dimensions[1] / 100)):
        for j in range(math.ceil(video_dimensions[0] / 100)):
            stderr = subprocess.PIPE
            try:
                await async_check_output(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        f"{tempdir}/{filename}",
                        "-vf",
                        f"crop=100:100:{j * 100}:{i * 100}",
                        f"{tempdir}/tile{i}_{j}.webm",
                        "-crf",
                        "40",
                        "-c:v",
                        "libvpx-vp9",
                        "-pix_fmt",
                        "yuva420p",
                        "-metadata",
                        "title=@itosbot",
                    ],
                    stderr=stderr,
                )
            except subprocess.CalledProcessError as e:
                print(e.stderr.decode("utf-8"))
                raise ConversionError("Something went wrong")
            usefull_tiles.append(f"{tempdir}/tile{i}_{j}.webm")

    # check file size
    # if it's more than 64kb, reduce quality
    for file in os.listdir(tempdir):
        if file.startswith("tile") and os.path.getsize(f"{tempdir}/{file}") > 64 * 1024:
            # no need to try uploading it, it will fail
            raise ConversionError("File is too big")
    return usefull_tiles
