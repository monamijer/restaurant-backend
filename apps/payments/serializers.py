from rest_framework import serializers

from apps.core.fields import CURRENCY_CODE

from .models import Payment, PaymentMethod

MAX_TOKEN_LENGTH = 100


class PaymentSerializer(serializers.ModelSerializer):
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id",
            "order",
            "method",
            "amount",
            "status",
            "reference",
            "paid_at",
            "created_at",
            "currency",
        )
        read_only_fields = fields

    def get_currency(self, payment):
        return CURRENCY_CODE


class PaymentCreateSerializer(serializers.Serializer):
    """There is deliberately no amount and no status field: the server decides both."""

    order = serializers.IntegerField(min_value=1)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    payment_token = serializers.CharField(
        required=False, allow_blank=True, max_length=MAX_TOKEN_LENGTH
    )

    def validate(self, attrs):
        return {
            "order_id": attrs["order"],
            "method": attrs["method"],
            "token": attrs.get("payment_token", ""),
        }