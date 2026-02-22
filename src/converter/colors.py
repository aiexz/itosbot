from string import hexdigits

# Common color aliases accepted for the `b=` argument.
COLOR_NAME_MAP: dict[str, str] = {
    "black": "000000",
    "white": "ffffff",
    "red": "ff0000",
    "green": "00ff00",
    "blue": "0000ff",
    "yellow": "ffff00",
    "orange": "ffa500",
    "purple": "800080",
    "pink": "ffc0cb",
    "brown": "a52a2a",
    "cyan": "00ffff",
    "magenta": "ff00ff",
    "gray": "808080",
    "grey": "808080",
}


def normalize_hex_color(color: str | None) -> str | None:
    """Return a 6-char lowercase hex color without '#', or None if invalid."""
    if not color:
        return None

    value = color.strip().lower()
    if not value:
        return None

    value = COLOR_NAME_MAP.get(value, value)

    if value.startswith("#"):
        value = value[1:]

    if len(value) == 3 and all(ch in hexdigits for ch in value):
        value = "".join(ch * 2 for ch in value)

    if len(value) != 6 or not all(ch in hexdigits for ch in value):
        return None

    return value.lower()
