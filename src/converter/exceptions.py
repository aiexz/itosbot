class ConversionError(Exception):
    pass


class TileLimitError(ConversionError):
    """Raised when the image/video would create too many tiles (>50)"""
    pass


class DimensionError(ConversionError):
    """Raised when image/video dimensions are invalid"""
    pass
