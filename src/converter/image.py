import logging
import math
import numpy as np

from PIL import Image as PILImage
from PIL.Image import Image
from src.converter.colors import normalize_hex_color
from src.converter.exceptions import TileLimitError, DimensionError


def remove_background(image: Image, bg_color: str, similarity: float = 10, blend: float = 10) -> Image:
    """
    Remove background color from image
    :param image: Input image
    :param bg_color: Background color as hex or name (e.g., "#FFFFFF", "FFFFFF", "white")
    :param similarity: Color similarity threshold (0-100, default 10)
    :param blend: Blend amount for edge smoothing (0-100, default 10)
    :return: Image with background removed
    """
    # Convert image to RGBA if not already
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Resolve named colors and normalize to 6-char hex.
    normalized_color = normalize_hex_color(bg_color)
    if normalized_color is None:
        logging.warning(f"Invalid background color format: {bg_color}")
        return image
    target_r = int(normalized_color[0:2], 16)
    target_g = int(normalized_color[2:4], 16)
    target_b = int(normalized_color[4:6], 16)
    
    # Convert image to numpy array
    data = np.array(image)
    r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
    
    # Convert 0-100 scale to 0.0-1.0 scale
    similarity_normalized = similarity / 100.0
    blend_normalized = blend / 100.0
    
    # Calculate color distance without extra float64 copies
    dr = r.astype(np.int32) - target_r
    dg = g.astype(np.int32) - target_g
    db = b.astype(np.int32) - target_b
    sq_dist = dr * dr + dg * dg + db * db
    distance = np.sqrt(sq_dist * (1.0 / (255.0 ** 2 * 3)), dtype=np.float32)

    if blend_normalized > 0:
        is_bg_candidate = (distance < (similarity_normalized + blend_normalized)) | (a == 0)
    else:
        is_bg_candidate = (distance <= similarity_normalized) | (a == 0)

    # Pad by 1 pixel on all borders so (0, 0) connects to all 4 outer edges of the image
    h, w = distance.shape
    padded = np.zeros((h + 2, w + 2), dtype=np.uint8)
    padded[0, :] = 255
    padded[-1, :] = 255
    padded[:, 0] = 255
    padded[:, -1] = 255
    padded[1:h + 1, 1:w + 1][is_bg_candidate] = 255

    _scanline_floodfill(padded, 0, 0, 255, 128)
    connected = padded[1:h + 1, 1:w + 1] == 128

    if blend_normalized > 0:
        factor = np.clip((distance[connected] - similarity_normalized) / blend_normalized, 0, 1)
        data[:, :, 3][connected] = (a[connected] * factor).astype(np.uint8)
    else:
        to_remove = connected & (distance <= similarity_normalized)
        data[:, :, 3][to_remove] = 0
    return PILImage.fromarray(data)


def _scanline_floodfill(grid: np.ndarray, seed_x: int = 0, seed_y: int = 0, target_val: int = 255, fill_val: int = 128) -> None:
    """4-connected span-based scanline flood fill on uint8 grid in-place."""
    h, w = grid.shape
    stack = [(seed_x, seed_y)]
    while stack:
        x, y = stack.pop()
        row = grid[y]
        if row[x] != target_val:
            continue

        left_blocked = np.flatnonzero(row[:x] != target_val)
        x1 = 0 if len(left_blocked) == 0 else left_blocked[-1] + 1

        right_blocked = np.flatnonzero(row[x + 1:] != target_val)
        x2 = w - 1 if len(right_blocked) == 0 else x + right_blocked[0]

        row[x1:x2 + 1] = fill_val

        if y > 0:
            above = grid[y - 1, x1:x2 + 1]
            mask_above = above == target_val
            if np.any(mask_above):
                starts = np.flatnonzero(mask_above & ~np.r_[False, mask_above[:-1]])
                for sx in x1 + starts:
                    stack.append((int(sx), y - 1))

        if y < h - 1:
            below = grid[y + 1, x1:x2 + 1]
            mask_below = below == target_val
            if np.any(mask_below):
                starts = np.flatnonzero(mask_below & ~np.r_[False, mask_below[:-1]])
                for sx in x1 + starts:
                    stack.append((int(sx), y + 1))


def _fit_proportional(w: int, h: int, max_w: float, max_h: float, max_tiles: int = 50) -> tuple[int, int]:
    """Fit dimensions proportionally within max bounds and tile count (max_tiles)."""
    tiles_w = math.ceil(w / 100)
    tiles_h = math.ceil(h / 100)
    if w <= max_w and h <= max_h and tiles_w * tiles_h <= max_tiles:
        return w, h

    max_scale = min(1.0, max_w / w, max_h / h)
    best_scale = 0.0
    best_w, best_h = max(1, round(w * max_scale)), max(1, round(h * max_scale))

    limit_tw = max_tiles if math.isinf(max_w) else min(max_tiles, math.ceil(max_w / 100))
    for tw in range(1, limit_tw + 1):
        th = max_tiles // tw
        if th == 0:
            continue
        box_w = min(tw * 100, max_w)
        box_h = min(th * 100, max_h)
        scale = min(box_w / w, box_h / h, max_scale)
        if scale > best_scale:
            cand_w = max(1, round(w * scale))
            cand_h = max(1, round(h * scale))
            if math.ceil(cand_w / 100) * math.ceil(cand_h / 100) <= max_tiles:
                best_scale = scale
                best_w, best_h = cand_w, cand_h

    return best_w, best_h


def adjust_size(image: Image, custom_width: int = 0, custom_height: int = 0) -> Image:
    """
    Adjust image size to be max 50 tiles (100x100 each) and within 800x5000 for default.
    Preserves aspect ratio for default and single requested dimension.
    Explicit both dimensions enforces max 50 tiles.
    :param image:
    :param custom_width: Custom width in pixels (0 = auto)
    :param custom_height: Custom height in pixels (0 = auto)
    :return:
    """
    # check the image size
    aspect_ratio = image.width / image.height
    if 0.02 > aspect_ratio or aspect_ratio > 50:
        logging.debug("Image size is not ok", aspect_ratio)
        raise DimensionError("Image aspect ratio is not supported (must be between 0.02 and 50)")
    
    # Both dimensions specified - intentional sizing and tile limit enforcement
    if custom_width > 0 and custom_height > 0:
        max_tiles_width = math.ceil(custom_width / 100)
        max_tiles_height = math.ceil(custom_height / 100)
        total_tiles = max_tiles_width * max_tiles_height
        if total_tiles > 50:
            raise TileLimitError(f"Custom dimensions would create {total_tiles} tiles (max 50). Reduce width or height.")
        if image.size != (custom_width, custom_height):
            image = image.resize((custom_width, custom_height))
        return image

    # Single custom dimension - scale proportionally within 50 tiles
    if custom_width > 0:
        target_w = custom_width
        target_h = max(1, round(custom_width / aspect_ratio))
        final_w, final_h = _fit_proportional(target_w, target_h, max_w=target_w, max_h=float("inf"), max_tiles=50)
        if (final_w, final_h) != image.size:
            image = image.resize((final_w, final_h))
        return image

    if custom_height > 0:
        target_h = custom_height
        target_w = max(1, round(custom_height * aspect_ratio))
        final_w, final_h = _fit_proportional(target_w, target_h, max_w=float("inf"), max_h=target_h, max_tiles=50)
        if (final_w, final_h) != image.size:
            image = image.resize((final_w, final_h))
        return image

    # Default sizing: max 800 width, max 5000 height, max 50 tiles
    final_w, final_h = _fit_proportional(image.width, image.height, max_w=800, max_h=5000, max_tiles=50)
    if (final_w, final_h) != image.size:
        image = image.resize((final_w, final_h))
    return image


def convert_to_images(image: Image, custom_width: int = 0, custom_height: int = 0, bg_color: str | None = None, bg_similarity: float = 10, bg_blend: float = 10) -> tuple[list[Image], int, int]:
    """
    Slice image to 100x100 tiles
    :param image:
    :param custom_width: Custom width in pixels (0 = auto)
    :param custom_height: Custom height in pixels (0 = auto)
    :param bg_color: Background color to remove as hex or name (e.g., "#FFFFFF", "white")
    :param bg_similarity: Color similarity threshold (0-100, default 10)
    :param bg_blend: Blend amount for edge smoothing (0-100, default 10)
    :return: Tuple of (tiles, tiles_width, tiles_height)
    """
    # Convert image to RGBA if not already (preserves palette transparency)
    if image.mode != 'RGBA':
        image = image.convert('RGBA')

    # Remove background if color is specified
    if bg_color:
        image = remove_background(image, bg_color, bg_similarity, bg_blend)

    # Auto-crop fully transparent outer margins using alpha getbbox
    alpha = image.getchannel('A')
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("Image is completely transparent")
    if bbox != (0, 0, image.width, image.height):
        image = image.crop(bbox)
    image = adjust_size(image, custom_width, custom_height)
    tiles_width = math.ceil(image.width / 100)
    tiles_height = math.ceil(image.height / 100)
    transparent = PILImage.new("RGBA", (tiles_width * 100, tiles_height * 100),
                               (0,0,0,0))
    transparent.paste(image, (0, 0))
    image = transparent

    # now split image to tiles
    tiles = []
    for i in range(tiles_height):
        for j in range(tiles_width):
            tile = image.crop((j * 100, i * 100, (j + 1) * 100, (i + 1) * 100))
            tiles.append(tile)
    return tiles, tiles_width, tiles_height
