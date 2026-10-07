from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import UserFilter
from . import services
from .models import Role
from .permissions import IsAdminRole, IsStaffRole
from .queries import users_with_customer_stats
from .serializers import (
    SetPasswordSerializer,
    UserAdminSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
)


class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Staff read customers; administrators manage every account. No deletion: deactivate."""

    serializer_class = UserAdminSerializer
    filterset_class = UserFilter
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering_fields = ["created_at", "last_login", "orders_count", "total_spent", "last_order_at"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsStaffRole()]
        return [IsAdminRole()]

    def get_queryset(self):
        queryset = users_with_customer_stats()
        if self.request.user.role == Role.ADMIN:
            return queryset
        return queryset.filter(role=Role.CLIENT)  # Staff only ever see customers.

    def _read(self, pk):
        """Re-read through the annotated queryset so every response has the same shape."""
        return UserAdminSerializer(self.get_queryset().get(pk=pk)).data

    def create(self, request, *args, **kwargs):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.create_user_account(**serializer.validated_data)
        return Response(self._read(user.pk), status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        target = self.get_object()
        serializer = UserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_user(target.pk, actor=request.user, changes=serializer.validated_data)
        return Response(self._read(target.pk))

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        target = self.get_object()
        serializer = SetPasswordSerializer(data=request.data, context={"target": target})
        serializer.is_valid(raise_exception=True)
        services.set_user_password(target.pk, serializer.validated_data["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)