from datetime import time
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError

SINGLETON_PK = 1


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class RestaurantSettings(TimestampedModel):
    """Single-row configuration editable by the administrator."""

    name = models.CharField(max_length=120, default="Restaurant")
    timezone = models.CharField(max_length=64, default="UTC")
    opening_time = models.TimeField(default=time(9, 0))
    closing_time = models.TimeField(default=time(22, 0))
    slot_step_minutes = models.PositiveSmallIntegerField(default=30)
    min_reservation_minutes = models.PositiveSmallIntegerField(default=30)
    max_reservation_minutes = models.PositiveSmallIntegerField(default=180)
    pending_reservation_expiry_minutes = models.PositiveSmallIntegerField(default=30)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    queue_minutes_per_party = models.PositiveSmallIntegerField(default=10)

    class Meta:
        verbose_name_plural = "restaurant settings"
        constraints = [
            models.CheckConstraint(
                condition=Q(closing_time__gt=F("opening_time")),
                name="settings_closing_after_opening",
            ),
            models.CheckConstraint(
                condition=Q(slot_step_minutes__gt=0), name="settings_slot_step_positive"
            ),
            models.CheckConstraint(
                condition=Q(min_reservation_minutes__gt=0)
                & Q(min_reservation_minutes__lte=F("max_reservation_minutes")),
                name="settings_reservation_bounds_valid",
            ),
            models.CheckConstraint(
                condition=Q(tax_rate__gte=0) & Q(tax_rate__lte=100),
                name="settings_tax_rate_percentage",
            ),
            models.CheckConstraint(
                condition=Q(queue_minutes_per_party__gt=0),
                name="settings_queue_minutes_positive",
            ),            
            
        ]

    @classmethod
    def load(cls):
        settings, _ = cls.objects.get_or_create(pk=SINGLETON_PK)
        return settings

    @property
    def zone(self):
        return ZoneInfo(self.timezone)

    def clean(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValidationError({"timezone": "Unknown timezone."})
            
    def save(self, *args, **kwargs):
        self.pk = SINGLETON_PK  # Whatever the caller does, there is only one row.
        if self._state.adding:
            # An unsaved instance may overwrite the existing row: keep its creation date.
            existing_created_at = (
                type(self).objects.filter(pk=SINGLETON_PK)
                .values_list("created_at", flat=True)
                .first()
            )
            if existing_created_at is not None:
                self.created_at = existing_created_at
        super().save(*args, **kwargs)
    

    def delete(self, *args, **kwargs):
        raise ProtectedError("Restaurant settings cannot be deleted.", {self})

    def __str__(self):
        return self.name