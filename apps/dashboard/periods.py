"""Date ranges for the dashboard and the reports.

A period is a run of whole *local* days of the restaurant, converted to a half-open UTC
interval [start, end) for database filters."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from django.utils import timezone

DEFAULT_RANGE_DAYS = 30
MAX_RANGE_DAYS = 366
DAYS_PER_WEEK = 7
SAFE_DAY_RANGE = (date(2000, 1, 1), date(2100, 12, 31))


@dataclass(frozen=True)
class Period:
    start_day: date  # First local day, inclusive.
    end_day: date  # Last local day, inclusive.
    start: datetime  # UTC instant, inclusive.
    end: datetime  # UTC instant, exclusive.
    zone: object

    @property
    def days(self):
        return (self.end_day - self.start_day).days + 1


def _day_start_utc(day, zone):
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)


def make_period(restaurant, start_day, end_day):
    zone = restaurant.zone
    return Period(
        start_day,
        end_day,
        _day_start_utc(start_day, zone),
        _day_start_utc(end_day + timedelta(days=1), zone),
        zone,
    )


def default_end_day(restaurant, now=None):
    return (now or timezone.now()).astimezone(restaurant.zone).date()


def previous_period(restaurant, period):
    """The run of days of the same length that ends the day before `period` starts."""
    end_day = period.start_day - timedelta(days=1)
    return make_period(restaurant, end_day - timedelta(days=period.days - 1), end_day)


def bucket_start(day, group_by):
    if group_by == "week":
        return day - timedelta(days=day.weekday())  # Weeks start on Monday.
    if group_by == "month":
        return day.replace(day=1)
    return day


def _next_bucket(day, group_by):
    if group_by == "week":
        return day + timedelta(days=DAYS_PER_WEEK)
    if group_by == "month":
        return (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return day + timedelta(days=1)


def bucket_starts(period, group_by):
    """Every bucket start covering the period, so empty buckets still appear in a chart."""
    current = bucket_start(period.start_day, group_by)
    while current <= period.end_day:
        yield current
        current = _next_bucket(current, group_by)