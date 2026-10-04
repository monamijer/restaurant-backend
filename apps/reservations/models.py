from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import TimestampedModel


class ReservationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"
    NO_SHOW = "no_show", "No show"
    EXPIRED = "expired", "Expired"


# # Statuses that hold a table slot. Overlap checks only look at these.
# ACTIVE_RESERVATION_STATUSES = (ReservationStatus.PENDING, ReservationStatus.CONFIRMED)


class Reservation(TimestampedModel):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reservations"
    )
    table = models.ForeignKey("tables.Table", on_delete=models.PROTECT, related_name="reservations")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    party_size = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12, choices=ReservationStatus.choices, default=ReservationStatus.PENDING
    )
    notes = models.TextField(blank=True)
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="A pending hold lapses at this instant."
    )

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["table", "starts_at", "ends_at"]),
            models.Index(fields=["status", "starts_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="reservation_ends_after_start"
            ),
            models.CheckConstraint(
                condition=Q(party_size__gt=0), name="reservation_party_size_positive"
            ),
        ]

    def __str__(self):
        return f"Reservation #{self.pk} table {self.table_id} at {self.starts_at:%Y-%m-%d %H:%M}"