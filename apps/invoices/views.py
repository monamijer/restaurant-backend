from django.http import FileResponse
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound

from apps.accounts.permissions import STAFF_ROLES

from .models import Invoice
from .serializers import InvoiceSerializer


class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Invoices are created by the payment service, never through the API."""

    serializer_class = InvoiceSerializer
    filterset_fields = ["order"]
    search_fields = ["invoice_number"]
    ordering_fields = ["issued_at", "total"]
    ordering = ["-issued_at"]

    def get_queryset(self):
        queryset = Invoice.objects.select_related("order")
        user = self.request.user
        if user.role in STAFF_ROLES:
            return queryset
        return queryset.filter(order__customer=user)

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request, pk=None):
        invoice = self.get_object()  # 404 for a customer asking about someone else's invoice
        if not invoice.pdf_file:
            raise NotFound("The invoice file is not available.")
        response = FileResponse(
            invoice.pdf_file.open("rb"),
            as_attachment=True,
            filename=f"{invoice.invoice_number}.pdf",
            content_type="application/pdf",
        )
        response["Cache-Control"] = "private, no-store"
        return response