from rest_framework import serializers

from apps.core.fields import CURRENCY_CODE

from .models import Invoice


class InvoiceSerializer(serializers.ModelSerializer):
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ("id", "order", "invoice_number", "total", "currency", "issued_at")
        read_only_fields = fields

    def get_currency(self, invoice):
        return CURRENCY_CODE