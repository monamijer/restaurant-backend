from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole, IsStaffRole
from apps.core.api import ProtectedDeleteMixin

from . import services
from .filters import TableFilter
from .models import Table
from .serializers import TableSerializer, TableStatusSerializer


class TableViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Table.objects.all()
    serializer_class = TableSerializer
    filterset_class = TableFilter
    search_fields = ["location"]
    ordering_fields = ["number", "capacity"]
    ordering = ["number"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            permission_classes = [IsAuthenticated]
        elif self.action == "set_status":
            permission_classes = [IsStaffRole]
        else:
            permission_classes = [IsAdminRole]
        return [permission() for permission in permission_classes]

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        table = self.get_object()
        serializer = TableStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_table_status(table, serializer.validated_data["status"])
        return Response(self.get_serializer(table).data)