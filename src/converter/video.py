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

async def get_video_length(filename: str) -> float:
    """Gets the length of a video file in seconds."""
    output = await async_check_output([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filename
    ], stderr=subprocess.DEVNULL)
    return float(output.decode("utf-8").strip())

async def modify_video_duration(filename: str) -> None:
    """Modifies the duration metadata in a WebM file to bypass duration checks."""
    with open(filename, "rb") as f:
        data = bytearray(f.read())
    
    DURATION_ID = b'\x44\x89'
    MICROVALUE = b'\x00\x40\xbf\x48\x00\x00'
    
    index = data.find(DURATION_ID)
    if index != -1:
        index += len(DURATION_ID)
        data[index:index + len(MICROVALUE)] = MICROVALUE
        
        with open(filename, "wb") as f:
            f.write(data)

async def reencode_tile_with_higher_compression(tile_filename: str, source_video: str, crop_filter: str, crf: int = 50) -> bool:
    """Re-encodes a tile with higher compression (higher CRF) to reduce file size.
    
    Args:
        tile_filename: Path to the tile file to re-encode
        source_video: Path to the source video
        crop_filter: The crop filter string (including colorkey if applicable)
        crf: CRF value to use (higher = more compression, lower quality)
    
    Returns:
        True if successful and file size is now acceptable, False otherwise
    """
    try:
        await async_check_output([
            "ffmpeg",
            "-y",
            "-i", source_video,
            "-vf", crop_filter,
            "-crf", str(crf),
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-metadata", "title=@itosbot",
            tile_filename
        ], stderr=subprocess.PIPE)
        
        await modify_video_duration(tile_filename)
        
        # Check if the file size is acceptable now
        return os.path.getsize(tile_filename) <= 64 * 1024
    except:
        return False

async def crop_tiles(tempdir: str, filename: str, width: int, height: int, bg_color: str | None = None, bg_similarity: float = 30, bg_blend: float = 0) -> List[str]:
    """Crops the video into 100x100 tiles and returns a list of tile filenames."""
    tiles = []
    num_rows = math.ceil(height / 100)
    num_cols = math.ceil(width / 100)
    
    # Build video filter string
    vf_parts = [f"crop=100:100:{0}:{0}"]  # placeholder, will be updated in loop
    
    # Add colorkey filter if background color is specified
    colorkey_filter = None
    if bg_color:
        # Parse hex color to format for ffmpeg
        bg_color_clean = bg_color.lstrip('#')
        if len(bg_color_clean) == 6:
            # Convert hex to 0xRRGGBB format for ffmpeg
            color_value = f"0x{bg_color_clean}"
            # Convert similarity (0-100) to ffmpeg similarity (0.0-1.0)
            similarity_value = bg_similarity / 100.0
            # Convert blend (0-100) to ffmpeg blend (0.0-1.0)
            blend_value = bg_blend / 100.0
            colorkey_filter = f"colorkey={color_value}:{similarity_value}:{blend_value}"
    
    oversized_tiles = []
    source_video = f"{tempdir}/{filename}"
    
    for i in range(num_rows):
        for j in range(num_cols):
            tile_filename = f"{tempdir}/tile{i}_{j}.webm"
            
            # Build filter string for this tile
            if colorkey_filter:
                vf_string = f"crop=100:100:{j*100}:{i*100},{colorkey_filter}"
            else:
                vf_string = f"crop=100:100:{j*100}:{i*100}"
            
            try:
                await async_check_output([
                    "ffmpeg",
                    "-y",
                    "-i", source_video,
                    "-vf", vf_string,
                    "-crf", "40",
                    "-c:v", "libvpx-vp9",
                    "-pix_fmt", "yuva420p",
                    "-metadata", "title=@itosbot",
                    tile_filename
                ], stderr=subprocess.PIPE)
            #     WHY DOES ARGUMENT ORDER FOR OUTPUT MATTER? IF NOT LAST FFMPEG WILL NOT FORCE PIX_FMT
            except subprocess.CalledProcessError as e:
                raise ConversionError("Something went wrong during tile cropping") from e
            
            # Modify duration metadata to bypass duration checks
            await modify_video_duration(tile_filename)
            
            # Check file size and track oversized tiles
            file_size = os.path.getsize(tile_filename)
            if file_size > 64 * 1024:
                oversized_tiles.append((tile_filename, vf_string, file_size))
            
            tiles.append(tile_filename)
    
    # Try to fix oversized tiles with higher compression
    if oversized_tiles:
        max_size = max(size for _, size in oversized_tiles)
        max_size_kb = max_size / 1024
        raise ConversionError(
            f"Video quality is too high for Telegram's limits. "
            f"Largest tile: {max_size_kb:.1f}KB (max: 64KB). "
            f"Try a shorter video, lower resolution, or simpler content."
            )
    
    return tiles


async def convert_video(video: BinaryIO, custom_width: int = 0, bg_color: str | None = None, bg_similarity: float =
20, bg_blend: float = 0) -> List[str]:
    """Converts an input video into a set of cropped tile video files.
    
    Args:
        video: Input video file as BinaryIO
        custom_width: Custom width in pixels (0 = auto)
        bg_color: Background color to remove in hex format (e.g., "#FFFFFF")
        bg_similarity: Color similarity threshold (0-100, default 20)
        bg_blend: Blend amount for edge smoothing (0-100, default 0)
    
    Returns:
        List of tile filenames
    """
    tempdir = tempfile.mkdtemp()
    filename = "video.mp4"
    with open(f"{tempdir}/{filename}", "wb") as f:
        f.write(video.read())

    width, height = await probe_video_dimensions(tempdir, filename)
    
    # Apply custom width if specified
    if custom_width > 0:
        aspect_ratio = width / height
        custom_height = max(int(custom_width / aspect_ratio), 100)
        
        # Ensure we don't exceed 50 tiles (100x100 each)
        max_tiles_width = math.ceil(custom_width / 100)
        max_tiles_height = math.ceil(custom_height / 100)
        total_tiles = max_tiles_width * max_tiles_height
        
        if total_tiles > 50:
            # Adjust height to fit within 50 tiles
            max_allowed_height = (50 // max_tiles_width) * 100
            custom_height = min(custom_height, max_allowed_height)
        
        # Ensure minimum dimensions and even numbers
        custom_width = max(custom_width, 100)
        custom_height = max(custom_height, 100)
        custom_width, custom_height = await ensure_even_dimensions(custom_width, custom_height)
        
        # Apply the custom dimensions
        new_filename = "video_custom.mp4"
        await scale_video(tempdir, filename, new_filename, f"scale={custom_width}:{custom_height}")
        filename = new_filename
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

    tiles = await crop_tiles(tempdir, filename, width, height, bg_color, bg_similarity, bg_blend)
    return tiles
