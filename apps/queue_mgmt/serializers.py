from rest_framework import serializers

from apps.accounts.models import PHONE_VALIDATOR
from apps.accounts.permissions import STAFF_ROLES

from . import services
from .models import QueueTicket

MAX_PARTY_SIZE = 20
MAX_NAME_LENGTH = 150
MAX_PHONE_LENGTH = 20


class QueueTicketSerializer(serializers.ModelSerializer):
    """`position` and `estimated_wait_minutes` are live; `quoted_wait_minutes` is the
    estimate that was given when the party joined."""

    position = serializers.SerializerMethodField()
    estimated_wait_minutes = serializers.SerializerMethodField()
    quoted_wait_minutes = serializers.IntegerField(source="estimated_wait_time", read_only=True)

    class Meta:
        model = QueueTicket
        fields = (
            "id",
            "customer",
            "customer_name",
            "phone",
            "party_size",
            "status",
            "position",
            "estimated_wait_minutes",
            "quoted_wait_minutes",
            "created_at",
            "called_at",
            "completed_at",
        )
        read_only_fields = fields

    def get_position(self, ticket):
        return self.context["positions"].get(ticket.pk)

    def get_estimated_wait_minutes(self, ticket):
        return services.estimate_wait_minutes(
            self.get_position(ticket), self.context["restaurant_settings"]
        )


class QueueJoinSerializer(serializers.Serializer):
    """Customers join for themselves; staff register a walk-in guest by name."""

    customer_name = serializers.CharField(
        required=False, allow_blank=True, max_length=MAX_NAME_LENGTH
    )
    phone = serializers.CharField(
        required=False, allow_blank=True, max_length=MAX_PHONE_LENGTH, validators=[PHONE_VALIDATOR]
    )
    party_size = serializers.IntegerField(min_value=1, max_value=MAX_PARTY_SIZE)

    def validate(self, attrs):
        user = self.context["request"].user
        if user.role in STAFF_ROLES:
            name = attrs.get("customer_name", "").strip()
            if not name:
                raise serializers.ValidationError(
                    {"customer_name": ["The guest's name is required."]}
                )
            return {
                "customer": None,
                "name": name,
                "phone": attrs.get("phone", ""),
                "party_size": attrs["party_size"],
            }
        # For a customer the account is the identity: any submitted name is ignored.
        return {
            "customer": user,
            "name": user.full_name,
            "phone": attrs.get("phone") or user.phone,
            "party_size": attrs["party_size"],
        }