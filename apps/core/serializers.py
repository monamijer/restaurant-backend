from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import RestaurantSettings


class RestaurantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantSettings
        fields = (
            "name",
            "timezone",
            "opening_time",
            "closing_time",
            "slot_step_minutes",
            "min_reservation_minutes",
            "max_reservation_minutes",
            "pending_reservation_expiry_minutes",
            "tax_rate",
            "updated_at",
        )
        read_only_fields = ("updated_at",)
        extra_kwargs = {
            "slot_step_minutes": {"min_value": 1},
            "min_reservation_minutes": {"min_value": 1},
            "max_reservation_minutes": {"min_value": 1},
            "pending_reservation_expiry_minutes": {"min_value": 1},
            "tax_rate": {"min_value": 0, "max_value": 100},
        }

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise serializers.ValidationError("Unknown timezone.")
        return value

    def validate(self, attrs):
        def effective(field):
            """The value after this request: submitted if present, else the stored one."""
            return attrs.get(field, getattr(self.instance, field))

        if effective("closing_time") <= effective("opening_time"):
            raise serializers.ValidationError(
                {"closing_time": "Closing time must be after opening time."}
            )
        if effective("min_reservation_minutes") > effective("max_reservation_minutes"):
            raise serializers.ValidationError(
                {"min_reservation_minutes": "Minimum duration cannot exceed the maximum."}
            )
        return attrs