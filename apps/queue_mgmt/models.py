from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounts.models import PHONE_VALIDATOR


class QueueStatus(models.TextChoices):
    WAITING = "waiting", "Waiting"
    CALLED = "called", "Called"
    SEATED = "seated", "Seated"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "No show"


class QueueTicket(models.Model):
    """A place in the virtual queue. The position is deliberately NOT stored:
    it is derived from the tickets ahead, in one service, so it can never drift."""

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="queue_tickets",
        help_text="Empty for walk-in guests registered by staff.",
    )
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, validators=[PHONE_VALIDATOR])
    party_size = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=10, choices=QueueStatus.choices, default=QueueStatus.WAITING
    )
    estimated_wait_time = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Minutes, estimated when the ticket was issued."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    called_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["status", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(party_size__gt=0), name="queueticket_party_size_positive"
            ),
        ]

    def __str__(self):
        return f"Ticket #{self.pk} {self.customer_name}"