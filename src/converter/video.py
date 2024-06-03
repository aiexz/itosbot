import io
import math
import os
import subprocess
import tempfile
from typing import BinaryIO

import PIL
from PIL.Image import Image

from src.converter.exceptions import ConversionError


def convert_video(video: BinaryIO):
    tempdir = tempfile.mkdtemp()
    filename = "video.mp4"
    with open(f"{tempdir}/{filename}", "wb") as f:
        f.write(video.read())
    video_dimensions = tuple(
        map(
            int,
            (
                subprocess.check_output(
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
                )
                .decode("utf-8")
                .split("x")
            ),
        )
    )
    if video_dimensions[0] > 100 or video_dimensions[1] > 100:
        # simillar code as in converter/image.py
        if video_dimensions[0] > 800:
            new_filename = "video_1.mp4"
            subprocess.check_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    f"{tempdir}/{filename}",
                    "-an",
                    "-vf",
                    "scale=800:-1",
                    f"{tempdir}/{new_filename}",
                ],
                stderr=subprocess.DEVNULL,
            )
            filename = new_filename
            video_dimensions = tuple(
                map(
                    int,
                    (
                        subprocess.check_output(
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
                        )
                        .decode("utf-8")
                        .split("x")
                    ),
                )
            )  # call to get new dimensions is less than 0.1s, so it's ok

        if video_dimensions[1] > 5000:
            new_filename = "video_2.mp4"
            subprocess.check_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    f"{tempdir}/{filename}",
                    "-an",
                    "-vf",
                    "scale=-1:5000",
                    f"{tempdir}/{new_filename}",
                ],
                stderr=subprocess.DEVNULL,
            )
            filename = new_filename
            video_dimensions = tuple(
                map(
                    int,
                    (
                        subprocess.check_output(
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
                        )
                        .decode("utf-8")
                        .split("x")
                    ),
                )
            )

        aspect_ratio = video_dimensions[0] / video_dimensions[1]
        if aspect_ratio > 1:
            new_filename = "video_3.mp4"
            max_height = 50 / math.ceil(video_dimensions[0] / 100)
            subprocess.check_output(
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
            subprocess.check_output(
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
            subprocess.check_output(
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
        subprocess.check_output(
            [
                "ffmpeg",
                "-y",
                "-i",
                f"{tempdir}/{filename}",
                "-an"
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
                subprocess.check_output(
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
                )
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
                subprocess.check_output(
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
