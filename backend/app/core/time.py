from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return a naive UTC datetime for consistent MySQL storage/comparison."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
