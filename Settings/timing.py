from datetime import datetime, timezone


def now() -> datetime:
    """Current UTC time with year, month, day, hour and minute (seconds dropped)"""
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)
