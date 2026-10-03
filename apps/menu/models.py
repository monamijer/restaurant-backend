from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.fields import money_field
from apps.core.models import TimestampedModel
from apps.core.slugs import unique_slug


class Category(TimestampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Category, self.name, instance_pk=self.pk)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class MenuItem(TimestampedModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)
    price = money_field(validators=[MinValueValidator(Decimal("0.00"))])
    image = models.ImageField(upload_to="menu/", blank=True)
    is_available = models.BooleanField(default=True)
    preparation_time = models.PositiveSmallIntegerField(default=15, help_text="Minutes.")
    is_featured = models.BooleanField(default=False)
    allergens = models.JSONField(default=list, blank=True)
    calories = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["category", "is_available"])]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="menuitem_price_non_negative"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(MenuItem, self.name, instance_pk=self.pk)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name