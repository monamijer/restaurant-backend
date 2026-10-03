from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminOrReadOnly, IsStaffRole
from apps.core.api import ProtectedDeleteMixin

from .filters import MenuItemFilter
from .models import Category, MenuItem
from .serializers import AvailabilitySerializer, CategorySerializer, MenuItemSerializer


class CategoryViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None  # A small, bounded set that the menu UI always loads whole.
    search_fields = ["name"]


class MenuItemViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = MenuItem.objects.select_related("category")
    serializer_class = MenuItemSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = MenuItemFilter
    search_fields = ["name", "description", "category__name"]
    ordering_fields = ["name", "price", "created_at", "preparation_time"]
    ordering = ["name"]

    @action(detail=True, methods=["post"], url_path="set-availability", permission_classes=[IsStaffRole])
    def set_availability(self, request, pk=None):
        """Staff may only flip availability: an item can run out mid-service."""
        item = self.get_object()
        serializer = AvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.is_available = serializer.validated_data["is_available"]
        item.save(update_fields=["is_available", "updated_at"])
        return Response(self.get_serializer(item).data)