from rest_framework import serializers

from apps.accounts.models import PHONE_VALIDATOR

from . import services
from .models import Order, OrderItem, OrderStatus, OrderType

from apps.accounts.permissions import STAFF_ROLES
from apps.tables import qr

MAX_QUANTITY = 50
MAX_LINES = 50
MAX_INSTRUCTIONS_LENGTH = 255
MAX_TEXT_LENGTH = 500
MAX_PHONE_LENGTH = 20
MAX_TOKEN_LENGTH = 300


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
    """On-site ordering: a customer proves presence with the table's QR token, staff may
    name the table directly."""

    order_type = serializers.ChoiceField(choices=OrderType.choices)
    table = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    table_token = serializers.CharField(
        required=False, allow_blank=True, max_length=MAX_TOKEN_LENGTH
    )
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

    def _resolve_table(self, attrs):
        is_staff = self.context["request"].user.role in STAFF_ROLES
        table_id, token = attrs.get("table"), attrs.get("table_token", "")
        if token and table_id is not None:
            raise serializers.ValidationError({"table": ["Send a table or a QR token, not both."]})
        if token:
            return qr.resolve_token(token).pk
        if table_id is not None and not is_staff:
            raise serializers.ValidationError(
                {"table": ["Customers order on site by scanning the table's QR code."]}
            )
        if table_id is None and attrs["order_type"] == OrderType.DINE_IN and not is_staff:
            raise serializers.ValidationError(
                {"table_token": ["Scan the table's QR code to order on site."]}
            )
        return table_id

    def validate(self, attrs):
        """Reshape the payload into the keyword arguments of `services.create_order`."""
        return {
            "order_type": attrs["order_type"],
            "table_id": self._resolve_table(attrs),
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