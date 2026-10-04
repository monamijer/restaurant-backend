from datetime import UTC, datetime, time, timedelta

import django_filters

from apps.core.models import RestaurantSettings

from .models import Reservation


class ReservationFilter(django_filters.FilterSet):
    date = django_filters.DateFilter(method="filter_date")

    class Meta:
        model = Reservation
        fields = ["status", "table"]

    def filter_date(self, queryset, name, value):
        """Reservations starting during the given *local* day of the restaurant."""
        zone = RestaurantSettings.load().zone
        day_start = datetime.combine(value, time.min).replace(tzinfo=zone).astimezone(UTC)
        next_day = datetime.combine(value + timedelta(days=1), time.min)
        day_end = next_day.replace(tzinfo=zone).astimezone(UTC)
        return queryset.filter(starts_at__gte=day_start, starts_at__lt=day_end)