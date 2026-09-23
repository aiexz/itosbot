import struct
import logging
import math
import os
import shutil
import subprocess
import tempfile
import asyncio
from typing import BinaryIO, Tuple, List


from src.converter.colors import normalize_hex_color
from src.converter.exceptions import ConversionError, TileLimitError


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

def _iter_ebml_elements(data: bytes | bytearray, start: int, end: int):
    """Yields (element_id, payload_start, payload_size) for elements in data[start:end]."""
    pos = start
    while pos < end:
        b0 = data[pos]
        if b0 == 0:
            break
        mask = 0x80
        id_len = 1
        while not (b0 & mask):
            mask >>= 1
            id_len += 1
        if pos + id_len > end:
            break
        elem_id = 0
        for i in range(id_len):
            elem_id = (elem_id << 8) | data[pos + i]

        size_pos = pos + id_len
        if size_pos >= end:
            break
        s0 = data[size_pos]
        if s0 == 0:
            break
        mask = 0x80
        size_len = 1
        while not (s0 & mask):
            mask >>= 1
            size_len += 1
        if size_pos + size_len > end:
            break

        raw_size = 0
        for i in range(size_len):
            raw_size = (raw_size << 8) | data[size_pos + i]
        raw_size &= (1 << (7 * size_len)) - 1

        payload_start = size_pos + size_len
        is_unknown = (raw_size == ((1 << (7 * size_len)) - 1))
        if is_unknown:
            payload_size = end - payload_start
            yield elem_id, payload_start, payload_size
            break
        else:
            payload_size = raw_size
            if payload_start + payload_size > end:
                break
            yield elem_id, payload_start, payload_size
            pos = payload_start + payload_size


async def modify_video_duration(filename: str) -> None:
    """Modifies the container duration metadata in a WebM file to declare a duration <= 3 seconds."""
    with open(filename, "rb") as f:
        data = bytearray(f.read())

    timestamp_scale = 1_000_000  # Default: 1ms = 1,000,000 ns per EBML/Matroska spec
    duration_offset = None
    duration_size = None

    for seg_id, seg_payload, seg_size in _iter_ebml_elements(data, 0, len(data)):
        if seg_id == 0x18538067:  # Segment
            for sub_id, sub_payload, sub_size in _iter_ebml_elements(data, seg_payload, seg_payload + seg_size):
                if sub_id == 0x1549A966:  # Info
                    for child_id, c_payload, c_size in _iter_ebml_elements(data, sub_payload, sub_payload + sub_size):
                        if child_id == 0x2AD7B1:  # TimestampScale (uint)
                            scale_val = int.from_bytes(data[c_payload : c_payload + c_size], byteorder="big")
                            if scale_val > 0:
                                timestamp_scale = scale_val
                        elif child_id == 0x4489:  # Duration (float)
                            duration_offset = c_payload
                            duration_size = c_size
                    break
                elif sub_id == 0x1F43B675:  # Cluster starts
                    break
            break

    if duration_offset is None or duration_size not in (4, 8):
        raise ConversionError("Missing or invalid duration element in WebM container")

    if duration_size == 4:
        current_val = struct.unpack(">f", data[duration_offset : duration_offset + 4])[0]
    else:
        current_val = struct.unpack(">d", data[duration_offset : duration_offset + 8])[0]

    current_duration_s = current_val * timestamp_scale / 1_000_000_000.0
    if current_duration_s > 3.0:
        target_val = 3.0 * 1_000_000_000.0 / timestamp_scale
        if duration_size == 4:
            payload = struct.pack(">f", target_val)
        else:
            payload = struct.pack(">d", target_val)
        data[duration_offset : duration_offset + duration_size] = payload
        with open(filename, "wb") as f:
            f.write(data)

async def crop_tiles(tempdir: str, filename: str, width: int, height: int, bg_color: str | None = None, bg_similarity: float = 30, bg_blend: float = 0) -> List[str]:
    """Crops the video into 100x100 tiles and returns a list of tile filenames.

    ``width``/``height`` describe the desired output canvas: the source is decoded
    once, scaled to it, then split into every tile and encoded in the same ffmpeg run.
    """
    num_rows = math.ceil(height / 100)
    num_cols = math.ceil(width / 100)
    
    # Add colorkey filter if background color is specified
    colorkey_filter = None
    if bg_color:
        # Resolve named colors and normalize to 6-char hex.
        normalized_color = normalize_hex_color(bg_color)
        if normalized_color:
            # Convert hex to 0xRRGGBB format for ffmpeg
            color_value = f"0x{normalized_color}"
            # Convert similarity (0-100) to ffmpeg similarity (0.0-1.0)
            similarity_value = bg_similarity / 100.0
            # Convert blend (0-100) to ffmpeg blend (0.0-1.0)
            blend_value = bg_blend / 100.0
            colorkey_filter = f"colorkey={color_value}:{similarity_value}:{blend_value}"
        else:
            logging.warning("Invalid background color format: %s", bg_color)
    
    source_video = f"{tempdir}/{filename}"
    source_width, source_height = await probe_video_dimensions(tempdir, filename)
    
    # Shared prologue: one decode, one scale, and (if requested) one colorkey pass
    # feeding the whole tile grid, so nothing is re-encoded per tile.
    prologue = ""
    if (source_width, source_height) != (width, height):
        prologue += f"scale={width}:{height},"
    if colorkey_filter:
        prologue += f"{colorkey_filter},"
    
    tile_specs = [
        (f"t{i}_{j}", j * 100, i * 100)
        for i in range(num_rows)
        for j in range(num_cols)
    ]
    tiles = [f"{tempdir}/tile{i}_{j}.webm" for i in range(num_rows) for j in range(num_cols)]
    
    if len(tile_specs) == 1:
        tag, x, y = tile_specs[0]
        filter_complex = f"[0:v]{prologue}crop=100:100:{x}:{y}[{tag}]"
    else:
        labels = "".join(f"[s{k}]" for k in range(len(tile_specs)))
        parts = [f"[0:v]{prologue}split={len(tile_specs)}{labels}"]
        parts += [
            f"[s{k}]crop=100:100:{x}:{y}[{tag}]"
            for k, (tag, x, y) in enumerate(tile_specs)
        ]
        filter_complex = ";".join(parts)
    
    #     WHY DOES ARGUMENT ORDER FOR OUTPUT MATTER? IF NOT LAST FFMPEG WILL NOT FORCE PIX_FMT
    cmd = ["ffmpeg", "-y", "-i", source_video, "-filter_complex", filter_complex]
    for tile_filename, (tag, _, _) in zip(tiles, tile_specs):
        cmd += [
            "-map", f"[{tag}]",
            "-an",
            "-threads", "1",
            "-crf", "40",
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-metadata", "title=@itosbot",
            tile_filename,
        ]
    
    try:
        await async_check_output(cmd, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise ConversionError("Something went wrong during tile cropping") from e
    
    oversized_tiles = []
    for tile_filename in tiles:
        # Modify duration metadata to bypass duration checks
        await modify_video_duration(tile_filename)
        
        # Check file size and track oversized tiles
        file_size = os.path.getsize(tile_filename)
        if file_size > 64 * 1024:
            oversized_tiles.append(file_size)
    
    # Check for oversized tiles
    if oversized_tiles:
        max_size_kb = max(oversized_tiles) / 1024
        raise ConversionError(
            f"Video quality is too high for Telegram's limits. "
            f"Largest tile: {max_size_kb:.1f}KB (max: 64KB). "
            f"Try a shorter video, lower resolution, or simpler content."
            )
    
    return tiles


async def compute_output_dimensions(width: int, height: int, custom_width: int, custom_height: int) -> Tuple[int, int]:
    """Derives the final tile canvas arithmetically instead of re-encoding the video per step."""
    if custom_width > 0 or custom_height > 0:
        aspect_ratio = width / height

        # Determine final dimensions
        if custom_width > 0 and custom_height > 0:
            # Both specified - use both
            width = custom_width
            height = custom_height

            # Check tile limit when both dimensions are specified
            total_tiles = math.ceil(width / 100) * math.ceil(height / 100)
            if total_tiles > 50:
                raise TileLimitError(f"Custom dimensions would create {total_tiles} tiles (max 50). Reduce width or height.")
        elif custom_width > 0:
            # Only width specified - calculate height from aspect ratio
            width = custom_width
            height = max(int(custom_width / aspect_ratio), 100)
        else:
            # Only height specified - calculate width from aspect ratio
            height = custom_height
            width = max(int(custom_height * aspect_ratio), 100)

        # Ensure we don't exceed 50 tiles (100x100 each)
        max_tiles_width = math.ceil(width / 100)
        if max_tiles_width * math.ceil(height / 100) > 50:
            # Adjust height to fit within 50 tiles
            height = min(height, (50 // max_tiles_width) * 100)

        # Ensure minimum dimensions and even numbers
        width = max(width, 100)
        height = max(height, 100)
        width, height = await ensure_even_dimensions(width, height)

    if width > 100 or height > 100:
        # Scale if width exceeds 800
        if width > 800:
            width, height = await ensure_even_dimensions(800, height / (width / 800))

        # Scale if height exceeds 5000
        if height > 5000:
            width, height = await ensure_even_dimensions(width / (height / 5000), 5000)

        # Adjust video based on aspect ratio
        aspect_ratio = width / height
        if aspect_ratio > 1:
            max_height = 50 / math.ceil(width / 100)
            target_height = min(int(max_height) * 100, height)
            # Calculate width to maintain aspect ratio
            target_width = int(width * (target_height / height))
            width, height = await ensure_even_dimensions(target_width, target_height)
        elif aspect_ratio == 1:
            max_size = 50 / math.ceil(width / 100)
            target_size = min(int(max_size) * 100, width)
            width, height = await ensure_even_dimensions(target_size, target_size)
        else:
            max_width = 50 / math.ceil(height / 100)
            target_width = min(int(max_width) * 100, width)
            # Calculate height to maintain aspect ratio
            target_height = int(height * (target_width / width))
            width, height = await ensure_even_dimensions(target_width, target_height)

        # Snap up to the 100px grid when the total number of tiles is small
        if math.ceil(width / 100) * math.ceil(height / 100) <= 50:
            width, height = await ensure_even_dimensions(math.ceil(width / 100) * 100, math.ceil(height / 100) * 100)

    # Final check to ensure we don't exceed 50 cells
    num_cells = math.ceil(width / 100) * math.ceil(height / 100)
    if num_cells > 50:
        # Calculate scaling factor to get under 50 cells
        scale_factor = math.sqrt(50 / num_cells)
        width, height = await ensure_even_dimensions(int(width * scale_factor), int(height * scale_factor))

    return width, height


async def convert_video(video: BinaryIO, custom_width: int = 0, custom_height: int = 0, bg_color: str | None = None, bg_similarity: float = 20, bg_blend: float = 0) -> tuple[List[str], int, int]:
    """Converts an input video into a set of cropped tile video files.
    
    Args:
        video: Input video file as BinaryIO
        custom_width: Custom width in pixels (0 = auto)
        custom_height: Custom height in pixels (0 = auto)
        bg_color: Background color to remove as hex or name (e.g., "#FFFFFF", "white")
        bg_similarity: Color similarity threshold (0-100, default 20)
        bg_blend: Blend amount for edge smoothing (0-100, default 0)
    
    Returns:
        Tuple of (tiles, tiles_width, tiles_height)
    """
    tempdir = tempfile.mkdtemp()
    completed = False
    try:
        filename = "video.mp4"
        with open(f"{tempdir}/{filename}", "wb") as f:
            f.write(video.read())

        try:
            video_length = await get_video_length(f"{tempdir}/{filename}")
        except Exception as e:
            raise ConversionError("Failed to probe video duration or invalid video file") from e
        if video_length > 5.0:
            raise ConversionError(
                f"Video duration is {video_length:.1f} seconds. Maximum allowed duration is 5 seconds."
            )

        width, height = await probe_video_dimensions(tempdir, filename)
        width, height = await compute_output_dimensions(width, height, custom_width, custom_height)

        tiles_width = math.ceil(width / 100)
        tiles_height = math.ceil(height / 100)
        tiles = await crop_tiles(tempdir, filename, width, height, bg_color, bg_similarity, bg_blend)
        completed = True
        return tiles, tiles_width, tiles_height
    finally:
        if not completed:
            shutil.rmtree(tempdir, ignore_errors=True)
