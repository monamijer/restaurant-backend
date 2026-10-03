import django_filters

from .models import MenuItem


class MenuItemFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(field_name="category_id")
    category_slug = django_filters.CharFilter(field_name="category__slug")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")

    class Meta:
        model = MenuItem
        fields = ["is_available", "is_featured"]