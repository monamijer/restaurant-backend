from rest_framework import serializers

from apps.tables.models import Table

from . import services
from .models import Reservation

MAX_NOTES_LENGTH = 500


class ReservationSerializer(serializers.ModelSerializer):
    """Read model. `date` and `time` are the restaurant's local wall-clock values."""

    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    table_number = serializers.IntegerField(source="table.number", read_only=True)
    date = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    duration_minutes = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = (
            "id",
            "customer",
            "customer_name",
            "customer_email",
            "table",
            "table_number",
            "date",
            "time",
            "duration_minutes",
            "starts_at",
            "ends_at",
            "party_size",
            "status",
            "notes",
            "expires_at",
            "created_at",
        )
        read_only_fields = fields

    def _local_start(self, reservation):
        return reservation.starts_at.astimezone(self.context["restaurant_settings"].zone)

    def get_date(self, reservation):
        return self._local_start(reservation).date().isoformat()

    def get_time(self, reservation):
        return self._local_start(reservation).strftime("%H:%M")

    def get_duration_minutes(self, reservation):
        return int((reservation.ends_at - reservation.starts_at).total_seconds() // 60)


class ReservationCreateSerializer(serializers.Serializer):
    table = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    time = serializers.TimeField()
    duration_minutes = serializers.IntegerField(min_value=1)
    party_size = serializers.IntegerField(min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=MAX_NOTES_LENGTH)

    def validate(self, attrs):
        """Turn local date/time/duration into the UTC window the service works with."""
        starts_at, ends_at = services.build_window(
            self.context["restaurant_settings"],
            attrs["date"],
            attrs["time"],
            attrs["duration_minutes"],
        )
        return {
            "table_id": attrs["table"],
            "starts_at": starts_at,
            "ends_at": ends_at,
            "party_size": attrs["party_size"],
            "notes": attrs.get("notes", ""),
        }


class AvailabilityQuerySerializer(serializers.Serializer):
    date = serializers.DateField()
    party_size = serializers.IntegerField(min_value=1)
    duration_minutes = serializers.IntegerField(min_value=1)


class AvailableTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ("id", "number", "capacity", "location")


class AvailabilitySlotSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    time = serializers.TimeField(format="%H:%M")
    tables = AvailableTableSerializer(many=True)