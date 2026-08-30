from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


def get_business_timezone() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def get_business_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(tz=get_business_timezone())
    return to_business_datetime(value)


def get_business_today(now: datetime | None = None) -> date:
    return get_business_now(now).date()


def to_business_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    timezone = get_business_timezone()
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def to_business_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        converted = to_business_datetime(value)
        return converted.date() if converted else None
    return value


def business_day_range(value: date) -> tuple[datetime, datetime]:
    timezone = get_business_timezone()
    start = datetime.combine(value, time.min, tzinfo=timezone)
    next_start = datetime.combine(value + timedelta(days=1), time.min, tzinfo=timezone)
    return start, next_start
