import random
import string


def random_string(
    length: int = 5, chars: str = string.ascii_letters + string.digits
) -> str:
    return "".join(random.choice(chars) for _ in range(length))
