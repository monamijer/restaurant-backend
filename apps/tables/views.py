from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole, IsStaffRole
from apps.core.api import ProtectedDeleteMixin

from . import services
from .filters import TableFilter
from .models import Table
from .serializers import TableSerializer, TableStatusSerializer, ResolveQrSerializer

from django.db.models import F
from django.http import HttpResponse
from rest_framework.permissions import AllowAny

from apps.core.api import ConflictError
from apps.core.models import RestaurantSettings

from . import qr


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
        elif self.action == "resolve_qr":
            permission_classes = [AllowAny]            
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
    @action(detail=True, methods=["get"], url_path="qr-code")
    def qr_code(self, request, pk=None):
        """The table's QR code as a PNG, for administrators only."""
        table = self.get_object()
        response = HttpResponse(qr.render_png(table), content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="table-{table.number}-qr.png"'
        response["Cache-Control"] = "private, no-store"
        return response

    @action(detail=False, methods=["get"], url_path="qr-sheet")
    def qr_sheet(self, request):
        """Every table's QR code on printable A4 pages."""
        tables = list(Table.objects.order_by("number"))
        if not tables:
            raise ConflictError("There are no tables to print.")
        pdf = qr.render_sheet(tables, RestaurantSettings.load().name)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="table-qr-codes.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response

    @action(detail=True, methods=["post"], url_path="regenerate-qr")
    def regenerate_qr(self, request, pk=None):
        """Invalidate every QR code already printed for this table."""
        table = self.get_object()
        Table.objects.filter(pk=table.pk).update(qr_version=F("qr_version") + 1)
        table.refresh_from_db()
        return Response(self.get_serializer(table).data)

    @action(
        detail=False, methods=["post"], url_path="resolve-qr", authentication_classes=[]
    )
    def resolve_qr(self, request):
        """Public: turn a scanned token into the table it designates."""
        serializer = ResolveQrSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        table = qr.resolve_token(serializer.validated_data["token"], field="token")
        return Response(
            {
                "id": table.pk,
                "number": table.number,
                "capacity": table.capacity,
                "location": table.location,
            }
        )    