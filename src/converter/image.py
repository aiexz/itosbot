import logging
import math

from PIL.Image import Image


def adjust_size(image: Image) -> Image:
    """
    Adjust image size to be in range 100x100 - 800x5000 that is max 50 tiles in total
    :param image:
    :return:
    """
    # check the image size
    aspect_ratio = image.width / image.height
    if 0.02 > aspect_ratio or aspect_ratio > 50:
        logging.debug("Image size is not ok", aspect_ratio)
        raise ValueError("Image size is not ok", aspect_ratio)
    if image.width > 100 or image.height > 100:
        logging.debug("Resizing image")
        if image.width > 800:
            # adjust width to 800px
            image = image.resize((800, max(int(800 / aspect_ratio), 100)))
        if image.height > 5000:
            # adjust height to 5000px
            image = image.resize((max(int(5000 * aspect_ratio), 100), 5000))

        # now find max number of tiles for this image for minor side and resize to it
        if aspect_ratio > 1:
            max_height = 50 / math.ceil(image.width / 100)
            image = image.resize(
                (image.width, min(int(max_height) * 100, image.height))
            )
        if aspect_ratio == 1:
            max_size = 50 / math.ceil(image.width / 100)
            image = image.resize(
                (
                    min(int(max_size) * 100, image.width),
                    min(int(max_size) * 100, image.height),
                )
            )
        else:
            max_width = 50 / math.ceil(image.height / 100)
            image = image.resize((min(int(max_width) * 100, image.width), image.height))
    return image


def convert_to_images(image: Image) -> list[Image]:
    """
    Slice image to 100x100 tiles
    :param image:
    :return:
    """
    image = adjust_size(image)
    # now split image to tiles
    tiles = []
    for i in range(math.ceil(image.height / 100)):
        for j in range(math.ceil(image.width / 100)):
            tile = image.crop((j * 100, i * 100, (j + 1) * 100, (i + 1) * 100))
            tiles.append(tile)
    return tiles
