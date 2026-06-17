from datetime import datetime, timedelta, timezone

GMT_PLUS_5 = timezone(timedelta(hours=5))


def now_gmt5() -> datetime:
    """Current wall-clock time in GMT+5, stored as naive datetime."""
    return datetime.now(GMT_PLUS_5).replace(tzinfo=None)


def as_gmt5_aware(dt: datetime) -> datetime:
    """Interpret naive DB timestamps as GMT+5 for API serialization."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=GMT_PLUS_5)
    return dt.astimezone(GMT_PLUS_5)
