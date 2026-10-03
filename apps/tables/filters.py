import django_filters

from .models import Table


class TableFilter(django_filters.FilterSet):
    min_capacity = django_filters.NumberFilter(field_name="capacity", lookup_expr="gte")
    location = django_filters.CharFilter(field_name="location", lookup_expr="icontains")

    class Meta:
        model = Table
        fields = ["status", "number"]