import django_filters
from django.db.models import Q

from . import services
from .models import QueueTicket


class QueueTicketFilter(django_filters.FilterSet):
    active = django_filters.BooleanFilter(method="filter_active")

    class Meta:
        model = QueueTicket
        fields = ["status"]

    def filter_active(self, queryset, name, value):
        """active=true keeps waiting and called tickets; active=false keeps the finished ones."""
        active = Q(status__in=services.ACTIVE_STATUSES)
        return queryset.filter(active) if value else queryset.exclude(active)