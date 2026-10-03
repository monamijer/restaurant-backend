from django.db import models

from apps.core.fields import money_field


class InvoiceSequence(models.Model):
    """One counter row per year, locked in the same transaction as invoice creation (Phase 4)."""

    year = models.PositiveSmallIntegerField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.year}: {self.last_number}"


class Invoice(models.Model):
    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="invoice")
    invoice_number = models.CharField(max_length=20, unique=True)
    pdf_file = models.FileField(upload_to="invoices/%Y/", blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    total = money_field()

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.invoice_number