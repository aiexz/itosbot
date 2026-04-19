from datetime import datetime, timedelta, timezone
from math import ceil

_cooldowns: dict[int, datetime] = {}


def get_retry_until(user_id: int) -> datetime | None:
    now = datetime.now(timezone.utc)
    retry_until = _cooldowns.get(user_id)
    if retry_until is None:
        return None
    if retry_until <= now:
        _cooldowns.pop(user_id, None)
        return None
    return retry_until


def save_retry_after(user_id: int, retry_after_seconds: int | float) -> datetime:
    retry_until = datetime.now(timezone.utc) + timedelta(
        seconds=max(0, retry_after_seconds)
    )
    _cooldowns[user_id] = retry_until
    return retry_until


def format_retry_message(retry_until: datetime) -> str:
    now = datetime.now(timezone.utc)
    seconds_left = max(0, ceil((retry_until - now).total_seconds()))
    retry_at = retry_until.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        "Telegram is rate limiting sticker creation right now. "
        f"Please try again in {seconds_left} seconds, after {retry_at}."
    )
