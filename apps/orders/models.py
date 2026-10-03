from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Q

from apps.accounts.models import PHONE_VALIDATOR
from apps.core.fields import money_field
from apps.core.models import TimestampedModel


class OrderType(models.TextChoices):
    DINE_IN = "dine_in", "Dine in"
    TAKEAWAY = "takeaway", "Takeaway"
    DELIVERY = "delivery", "Delivery"


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class Order(TimestampedModel):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
    )
    table = models.ForeignKey(
        "tables.Table", on_delete=models.PROTECT, null=True, blank=True, related_name="orders"
    )
    order_type = models.CharField(
        max_length=10, choices=OrderType.choices, default=OrderType.DINE_IN
    )
    status = models.CharField(
        max_length=10, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    delivery_address = models.TextField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, validators=[PHONE_VALIDATOR])
    notes = models.TextField(blank=True)
    subtotal = money_field(default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    tax_amount = money_field(default=Decimal("0.00"))
    total = money_field(default=Decimal("0.00"))

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["customer", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total=F("subtotal") + F("tax_amount")),
                name="order_total_is_subtotal_plus_tax",
            ),
            models.CheckConstraint(condition=Q(total__gte=0), name="order_total_non_negative"),
        ]

    def __str__(self):
        return f"Order #{self.pk}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        "menu.MenuItem", on_delete=models.PROTECT, related_name="order_items"
    )
    item_name = models.CharField(max_length=150, help_text="Name at the time of ordering.")
    quantity = models.PositiveSmallIntegerField()
    unit_price = money_field(help_text="Price at the time of ordering.")
    subtotal = money_field()
    special_instructions = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="orderitem_quantity_min_one"),
            models.CheckConstraint(
                condition=Q(
                    subtotal=ExpressionWrapper(
                        F("quantity") * F("unit_price"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                ),
                name="orderitem_subtotal_is_quantity_times_price",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.item_name}"