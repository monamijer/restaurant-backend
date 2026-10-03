from django.db import models
from django.db.models import Q

from apps.core.models import TimestampedModel


class TableStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    OCCUPIED = "occupied", "Occupied"
    RESERVED = "reserved", "Reserved"
    CLEANING = "cleaning", "Cleaning"


class Table(TimestampedModel):
    number = models.PositiveSmallIntegerField(unique=True)
    capacity = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=10, choices=TableStatus.choices, default=TableStatus.AVAILABLE
    )
    location = models.CharField(max_length=60, blank=True)
    qr_code = models.ImageField(upload_to="tables/qr/", blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.CheckConstraint(condition=Q(capacity__gt=0), name="table_capacity_positive"),
        ]

    def __str__(self):
        return f"Table {self.number}"