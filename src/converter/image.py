import logging
import math
import numpy as np

from PIL import Image as PILImage
from PIL.Image import Image
from src.converter.exceptions import TileLimitError, DimensionError


def remove_background(image: Image, bg_color: str, similarity: float = 20, blend: float = 0) -> Image:
    """
    Remove background color from image
    :param image: Input image
    :param bg_color: Background color in hex format (e.g., "#FFFFFF" or "FFFFFF")
    :param similarity: Color similarity threshold (0-100, default 20)
    :param blend: Blend amount for edge smoothing (0-100, default 0)
    :return: Image with background removed
    """
    # Convert image to RGBA if not already
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Parse hex color
    bg_color = bg_color.lstrip('#')
    if len(bg_color) == 6:
        target_r = int(bg_color[0:2], 16)
        target_g = int(bg_color[2:4], 16)
        target_b = int(bg_color[4:6], 16)
    else:
        logging.warning(f"Invalid background color format: {bg_color}")
        return image
    
    # Convert image to numpy array
    data = np.array(image)
    r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
    
    # Convert 0-100 scale to 0.0-1.0 scale
    similarity_normalized = similarity / 100.0
    blend_normalized = blend / 100.0
    
    # Calculate color distance
    distance = np.sqrt(
        ((r.astype(float) - target_r) ** 2 +
         (g.astype(float) - target_g) ** 2 +
         (b.astype(float) - target_b) ** 2) / (255.0 ** 2 * 3)
    )
    
    # Create mask based on similarity
    if blend_normalized > 0:
        # Smooth transition
        mask = np.clip((distance - similarity_normalized) / blend_normalized, 0, 1)
        a = (a * mask).astype(np.uint8)
    else:
        # Hard edge
        mask = distance > similarity_normalized
        a = np.where(mask, a, 0).astype(np.uint8)
    
    # Update alpha channel
    data[:, :, 3] = a
    
    return PILImage.fromarray(data, 'RGBA')


def adjust_size(image: Image, custom_width: int = 0, custom_height: int = 0) -> Image:
    """
    Adjust image size to be in range 100x100 - 800x5000 that is max 50 tiles in total
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
    
    # Apply custom dimensions if specified
    if custom_width > 0 or custom_height > 0:
        # Determine final dimensions
        if custom_width > 0 and custom_height > 0:
            # Both specified - use both
            logging.debug(f"Applying custom width: {custom_width}px and height: {custom_height}px")
            final_width = custom_width
            final_height = custom_height
            
            # Check tile limit when both dimensions are specified
            max_tiles_width = math.ceil(final_width / 100)
            max_tiles_height = math.ceil(final_height / 100)
            total_tiles = max_tiles_width * max_tiles_height
            
            if total_tiles > 50:
                raise TileLimitError(f"Custom dimensions would create {total_tiles} tiles (max 50). Reduce width or height.")
        elif custom_width > 0:
            # Only width specified - calculate height from aspect ratio
            logging.debug(f"Applying custom width: {custom_width}px")
            final_width = custom_width
            final_height = max(int(custom_width / aspect_ratio), 100)
        else:
            # Only height specified - calculate width from aspect ratio
            logging.debug(f"Applying custom height: {custom_height}px")
            final_height = custom_height
            final_width = max(int(custom_height * aspect_ratio), 100)
        
        custom_width = final_width
        custom_height = final_height
        
        # Ensure we don't exceed 50 tiles (100x100 each)
        max_tiles_width = math.ceil(custom_width / 100)
        max_tiles_height = math.ceil(custom_height / 100)
        total_tiles = max_tiles_width * max_tiles_height
        
        if total_tiles > 50:
            # Adjust height to fit within 50 tiles
            max_allowed_height = (50 // max_tiles_width) * 100
            custom_height = min(custom_height, max_allowed_height)
            logging.debug(f"Adjusted height to {custom_height}px to stay within 50 tiles limit")
        
        # Ensure minimum dimensions
        custom_width = max(custom_width, 100)
        custom_height = max(custom_height, 100)
        
        image = image.resize((custom_width, custom_height))
        return image
    
    if image.width > 100 or image.height > 100:
        logging.debug("Resizing image")
        # Calculate final dimensions in one pass to avoid multiple resizes
        final_width = image.width
        final_height = image.height
        
        # Apply width constraint
        if final_width > 800:
            final_width = 800
            final_height = max(int(800 / aspect_ratio), 100)
        
        # Apply height constraint
        if final_height > 5000:
            final_height = 5000
            final_width = max(int(5000 * aspect_ratio), 100)

        # Apply tile constraint (max 50 tiles of 100x100 each)
        if aspect_ratio > 1:
            max_height = 50 / math.ceil(final_width / 100)
            final_height = min(int(max_height) * 100, final_height)
        elif aspect_ratio == 1:
            max_size = 50 / math.ceil(final_width / 100)
            final_width = min(int(max_size) * 100, final_width)
            final_height = min(int(max_size) * 100, final_height)
        else:
            max_width = 50 / math.ceil(final_height / 100)
            final_width = min(int(max_width) * 100, final_width)
        
        # Perform single resize operation
        if final_width != image.width or final_height != image.height:
            image = image.resize((final_width, final_height))
    return image


def convert_to_images(image: Image, custom_width: int = 0, custom_height: int = 0, bg_color: str | None = None, bg_similarity: float = 30, bg_blend: float = 0) -> list[Image]:
    """
    Slice image to 100x100 tiles
    :param image:
    :param custom_width: Custom width in pixels (0 = auto)
    :param custom_height: Custom height in pixels (0 = auto)
    :param bg_color: Background color to remove in hex format (e.g., "#FFFFFF")
    :param bg_similarity: Color similarity threshold (0-100, default 30)
    :param bg_blend: Blend amount for edge smoothing (0-100, default 0)
    :return:
    """
    # Remove background if color is specified
    if bg_color:
        image = remove_background(image, bg_color, bg_similarity, bg_blend)
    
    image = adjust_size(image, custom_width, custom_height)
    transparent = PILImage.new("RGBA", (math.ceil(image.width / 100) * 100, math.ceil(image.height / 100) * 100),
                               (0,0,0,0))
    transparent.paste(image, (0, 0))
    image = transparent

    # now split image to tiles
    tiles = []
    for i in range(math.ceil(image.height / 100)):
        for j in range(math.ceil(image.width / 100)):
            tile = image.crop((j * 100, i * 100, (j + 1) * 100, (i + 1) * 100))
            tiles.append(tile)
    return tiles
