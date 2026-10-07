from rest_framework import serializers

from .periods import (
    DEFAULT_RANGE_DAYS,
    MAX_RANGE_DAYS,
    SAFE_DAY_RANGE,
    default_end_day,
    make_period,
)
from datetime import timedelta

GROUP_BY_CHOICES = ("day", "week", "month")
DEFAULT_TOP_ITEMS = 10
MAX_TOP_ITEMS = 50


class PeriodQuerySerializer(serializers.Serializer):
    """?start=YYYY-MM-DD&end=YYYY-MM-DD&group_by=day|week|month&limit=10&export=csv

    Dates are local days of the restaurant. Missing dates default to the last 30 days.
    The context must carry `restaurant_settings`."""

    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    group_by = serializers.ChoiceField(choices=GROUP_BY_CHOICES, required=False, default="day")
    limit = serializers.IntegerField(
        required=False, min_value=1, max_value=MAX_TOP_ITEMS, default=DEFAULT_TOP_ITEMS
    )
    export = serializers.ChoiceField(choices=["csv"], required=False)

    def validate(self, attrs):
        restaurant = self.context["restaurant_settings"]
        low, high = SAFE_DAY_RANGE

        end = attrs.get("end") or default_end_day(restaurant)
        if not low <= end <= high:
            raise serializers.ValidationError({"end": ["This date is out of range."]})
        start = attrs.get("start") or end - timedelta(days=DEFAULT_RANGE_DAYS - 1)
        if not low <= start <= high:
            raise serializers.ValidationError({"start": ["This date is out of range."]})

        if start > end:
            raise serializers.ValidationError({"start": ["The start date must not be after the end date."]})
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            raise serializers.ValidationError(
                {"end": [f"A period covers at most {MAX_RANGE_DAYS} days."]}
            )
        attrs["period"] = make_period(restaurant, start, end)
        return attrs