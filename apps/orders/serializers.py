from rest_framework import serializers

from apps.accounts.models import PHONE_VALIDATOR

from . import services
from .models import Order, OrderItem, OrderStatus, OrderType

MAX_QUANTITY = 50
MAX_LINES = 50
MAX_INSTRUCTIONS_LENGTH = 255
MAX_TEXT_LENGTH = 500
MAX_PHONE_LENGTH = 20


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            "id",
            "menu_item",
            "item_name",
            "quantity",
            "unit_price",
            "subtotal",
            "special_instructions",
        )
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    """Read model. Every amount here was computed by the server and frozen at order time."""

    customer_name = serializers.SerializerMethodField()
    table_number = serializers.IntegerField(source="table.number", read_only=True, allow_null=True)
    items = OrderItemSerializer(many=True, read_only=True)
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "customer",
            "customer_name",
            "order_type",
            "status",
            "table",
            "table_number",
            "delivery_address",
            "contact_phone",
            "notes",
            "items",
            "subtotal",
            "tax_rate",
            "tax_amount",
            "total",
            "currency",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_customer_name(self, order):
        return order.customer.full_name if order.customer_id else ""

    def get_currency(self, order):
        return services.CURRENCY_CODE


class OrderLineSerializer(serializers.Serializer):
    """One requested dish. There is deliberately no price field: the server decides."""

    menu_item = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_QUANTITY)
    special_instructions = serializers.CharField(
        required=False, allow_blank=True, max_length=MAX_INSTRUCTIONS_LENGTH
    )


class OrderCreateSerializer(serializers.Serializer):
    order_type = serializers.ChoiceField(choices=OrderType.choices)
    table = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    delivery_address = serializers.CharField(
        required=False, allow_blank=True, max_length=MAX_TEXT_LENGTH
    )
    contact_phone = serializers.CharField(
        required=False, allow_blank=True, max_length=MAX_PHONE_LENGTH, validators=[PHONE_VALIDATOR]
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=MAX_TEXT_LENGTH)
    items = OrderLineSerializer(many=True, allow_empty=False)

    def validate_items(self, value):
        if len(value) > MAX_LINES:
            raise serializers.ValidationError(f"An order has at most {MAX_LINES} lines.")
        return value

    def validate(self, attrs):
        """Reshape the payload into the keyword arguments of `services.create_order`."""
        return {
            "order_type": attrs["order_type"],
            "table_id": attrs.get("table"),
            "delivery_address": attrs.get("delivery_address", ""),
            "contact_phone": attrs.get("contact_phone", ""),
            "notes": attrs.get("notes", ""),
            "lines": [
                {
                    "menu_item_id": line["menu_item"],
                    "quantity": line["quantity"],
                    "special_instructions": line.get("special_instructions", ""),
                }
                for line in attrs["items"]
            ],
        }


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)