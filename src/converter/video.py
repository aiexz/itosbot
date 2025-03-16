import io
import math
import os
import subprocess
import tempfile
import asyncio
from typing import BinaryIO, Tuple, List

import PIL
from PIL.Image import Image

from src.converter.exceptions import ConversionError


async def async_check_output(cmd, stderr=None) -> bytes:
    """Run a subprocess command asynchronously and return its stdout output as bytes."""
    if stderr == subprocess.DEVNULL:
        stderr = asyncio.subprocess.DEVNULL
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=stderr)
    out, err = await proc.communicate()
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
    return out


async def probe_video_dimensions(tempdir: str, filename: str) -> Tuple[int, int]:
    """Probes a video file and returns its dimensions (width, height)."""
    output = await async_check_output([
        "ffprobe",
        "-v", "error",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        "-i", f"{tempdir}/{filename}"
    ], stderr=subprocess.DEVNULL)
    dims = output.decode("utf-8").strip().split("x")
    return int(dims[0]), int(dims[1])


async def ensure_even_dimensions(width: float, height: float) -> Tuple[int, int]:
    """Ensures both width and height are even numbers."""
    width = int(width)
    height = int(height)
    # Make sure both dimensions are even
    width = width - (width % 2)
    height = height - (height % 2)
    # Ensure dimensions are at least 2 pixels
    width = max(2, width)
    height = max(2, height)
    return width, height


async def scale_video(tempdir: str, input_filename: str, output_filename: str, scale_filter: str) -> None:
    """Scales a video using ffmpeg with the specified scale filter."""
    await async_check_output([
        "ffmpeg",
        "-y",
        "-i", f"{tempdir}/{input_filename}",
        "-an",
        "-vf", scale_filter,
        f"{tempdir}/{output_filename}"
    ], stderr=subprocess.DEVNULL)


async def crop_tiles(tempdir: str, filename: str, width: int, height: int) -> List[str]:
    """Crops the video into 100x100 tiles and returns a list of tile filenames."""
    tiles = []
    num_rows = math.ceil(height / 100)
    num_cols = math.ceil(width / 100)
    for i in range(num_rows):
        for j in range(num_cols):
            tile_filename = f"{tempdir}/tile{i}_{j}.webm"
            try:
                await async_check_output([
                    "ffmpeg",
                    "-y",
                    "-i", f"{tempdir}/{filename}",
                    "-vf", f"crop=100:100:{j*100}:{i*100}",
                    tile_filename,
                    "-crf", "40",
                    "-c:v", "libvpx-vp9",
                    "-pix_fmt", "yuva420p",
                    "-metadata", "title=@itosbot",
                ], stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                raise ConversionError("Something went wrong during tile cropping") from e
            tiles.append(tile_filename)
    # Verify file size for each tile
    for tile in tiles:
        if os.path.getsize(tile) > 64 * 1024:
            raise ConversionError("Tile file is too big")
    return tiles


async def convert_video(video: BinaryIO) -> List[str]:
    """Converts an input video into a set of cropped tile video files."""
    tempdir = tempfile.mkdtemp()
    filename = "video.mp4"
    with open(f"{tempdir}/{filename}", "wb") as f:
        f.write(video.read())

    width, height = await probe_video_dimensions(tempdir, filename)

    if width > 100 or height > 100:
        # Scale if width exceeds 800
        if width > 800:
            scaled = height / (width / 800)
            resized, _ = await ensure_even_dimensions(800, scaled)
            new_filename = "video_1.mp4"
            await scale_video(tempdir, filename, new_filename, f"scale={resized}:{_}")
            filename = new_filename
            width, height = await probe_video_dimensions(tempdir, filename)

        # Scale if height exceeds 5000
        if height > 5000:
            scaled = width / (height / 5000)
            resized, _ = await ensure_even_dimensions(scaled, 5000)
            new_filename = "video_2.mp4"
            await scale_video(tempdir, filename, new_filename, f"scale={resized}:{_}")
            filename = new_filename
            width, height = await probe_video_dimensions(tempdir, filename)

        # Adjust video based on aspect ratio
        aspect_ratio = width / height
        if aspect_ratio > 1:
            new_filename = "video_3.mp4"
            max_height = 50 / math.ceil(width / 100)
            target_height = min(int(max_height) * 100, height)
            # Calculate width to maintain aspect ratio
            target_width = int(width * (target_height / height))
            target_width, target_height = await ensure_even_dimensions(target_width, target_height)
            await scale_video(tempdir, filename, new_filename, f"scale={target_width}:{target_height}")
            filename = new_filename
        elif aspect_ratio == 1:
            new_filename = "video_3.mp4"
            max_size = 50 / math.ceil(width / 100)
            target_size = min(int(max_size) * 100, width)
            target_width, target_height = await ensure_even_dimensions(target_size, target_size)
            await scale_video(tempdir, filename, new_filename, f"scale={target_width}:{target_height}")
            filename = new_filename
        else:
            new_filename = "video_3.mp4"
            max_width = 50 / math.ceil(height / 100)
            target_width = min(int(max_width) * 100, width)
            # Calculate height to maintain aspect ratio
            target_height = int(height * (target_width / width))
            target_width, target_height = await ensure_even_dimensions(target_width, target_height)
            await scale_video(tempdir, filename, new_filename, f"scale={target_width}:{target_height}")
            filename = new_filename

        # Further scaling if the total number of tiles is small
        width, height = await probe_video_dimensions(tempdir, filename)
        if math.ceil(width / 100) * math.ceil(height / 100) <= 50:
            new_filename = "video_4.webm"
            target_width = math.ceil(width / 100) * 100
            target_height = math.ceil(height / 100) * 100
            target_width, target_height = await ensure_even_dimensions(target_width, target_height)
            await scale_video(tempdir, filename, new_filename, f"scale={target_width}:{target_height}")
            filename = new_filename
            width, height = await probe_video_dimensions(tempdir, filename)

    # Final check to ensure we don't exceed 50 cells
    num_cells = math.ceil(width / 100) * math.ceil(height / 100)
    if num_cells > 50:
        # Calculate scaling factor to get under 50 cells
        scale_factor = math.sqrt(50 / num_cells)
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        new_width, new_height = await ensure_even_dimensions(new_width, new_height)
        
        new_filename = "video_final.webm"
        await scale_video(tempdir, filename, new_filename, f"scale={new_width}:{new_height}")
        filename = new_filename
        width, height = await probe_video_dimensions(tempdir, filename)

    tiles = await crop_tiles(tempdir, filename, width, height)
    return tiles
