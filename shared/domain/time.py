from __future__ import annotations

from datetime import datetime, timezone

from .errors import InvalidTimestampError


def normalize_timestamp(value: datetime | str) -> datetime:
    try:
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif isinstance(value, datetime):
            parsed = value
        else:
            raise TypeError("timestamp must be a datetime or ISO 8601 string")
    except (TypeError, ValueError) as error:
        raise InvalidTimestampError(f"Invalid timestamp: {value!r}") from error

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)
