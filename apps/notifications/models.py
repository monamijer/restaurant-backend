from django.conf import settings
from django.db import models


class NotificationType(models.TextChoices):
    RESERVATION = "reservation", "Reservation"
    QUEUE = "queue", "Queue"
    ORDER = "order", "Order"
    PAYMENT = "payment", "Payment"
    SYSTEM = "system", "System"


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=12, choices=NotificationType.choices)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "created_at"])]

    def __str__(self):
        return f"{self.type} for user {self.user_id}"