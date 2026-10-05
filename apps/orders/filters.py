import django_filters
from django.db.models import Q

from . import services
from .models import Order


class OrderFilter(django_filters.FilterSet):
    active = django_filters.BooleanFilter(method="filter_active")

    class Meta:
        model = Order
        fields = ["status", "order_type", "table"]

    def filter_active(self, queryset, name, value):
        """active=true keeps orders still in progress; active=false keeps finished ones."""
        in_progress = Q(status__in=services.OPEN_STATUSES)
        return queryset.filter(in_progress) if value else queryset.exclude(in_progress)