import uuid

from django.db import models
from django.db.models import Q

from apps.core.fields import money_field

REFERENCE_PREFIX = "PAY-"
REFERENCE_LENGTH = 12


def generate_payment_reference():
    return f"{REFERENCE_PREFIX}{uuid.uuid4().hex[:REFERENCE_LENGTH].upper()}"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    MOBILE_MONEY = "mobile_money", "Mobile money"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class Payment(models.Model):
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=12, choices=PaymentMethod.choices)
    amount = money_field()
    status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    reference = models.CharField(
        max_length=32, unique=True, default=generate_payment_reference, editable=False
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
            models.CheckConstraint(
                condition=~Q(status="paid") | Q(paid_at__isnull=False),
                name="payment_paid_requires_paid_at",
            ),
        ]

    def __str__(self):
        return self.reference