from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Moscow")


def local_dt_to_utc_naive(day: date, value: time, timezone_name: str) -> datetime:
    local = datetime.combine(day, value).replace(tzinfo=zone(timezone_name))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def aware_to_utc_naive(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone(timezone_name))
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def utc_naive_to_local(value: datetime, timezone_name: str) -> datetime:
    return value.replace(tzinfo=timezone.utc).astimezone(zone(timezone_name))


def utc_naive_iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
