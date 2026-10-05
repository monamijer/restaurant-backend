from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import STAFF_ROLES, IsStaffRole

from . import services
from .filters import OrderFilter
from .models import Order
from .serializers import OrderCreateSerializer, OrderSerializer, OrderStatusSerializer


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Customers see and create their own orders; staff see and advance all of them."""

    serializer_class = OrderSerializer
    filterset_class = OrderFilter
    search_fields = ["customer__email", "customer__first_name", "customer__last_name", "contact_phone"]
    ordering_fields = ["created_at", "total"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Order.objects.select_related("customer", "table").prefetch_related("items")
        user = self.request.user
        if user.role in STAFF_ROLES:
            return queryset
        return queryset.filter(customer=user)

    def create(self, request, *args, **kwargs):
        serializer = OrderCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        # A customer orders for themselves; staff enter orders for guests without an account.
        customer = None if request.user.role in STAFF_ROLES else request.user
        order = services.create_order(customer=customer, **serializer.validated_data)
        return Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["post"],
        url_path="update-status",
        permission_classes=[IsStaffRole],
    )
    def update_status(self, request, pk=None):
        order = self.get_object()
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.update_status(order.pk, serializer.validated_data["status"])
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()  # 404 for a customer asking about someone else's order
        updated = services.cancel_order(order.pk, actor=request.user)
        return Response(self.get_serializer(updated).data)