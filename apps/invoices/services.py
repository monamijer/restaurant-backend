"""Invoice issuing: gapless sequential numbers and the stored PDF.

Numbering
---------
One counter row per year. `ensure_sequence` creates the row outside any transaction, so a
first-of-the-year race cannot trip over a transaction snapshot. `issue_invoice` then locks the
row, increments it and creates the invoice in the caller's transaction: a rollback undoes the
increment, so numbers never have gaps. Issuing is serialised by that lock, PDF included. At a
restaurant's volume that costs tens of milliseconds, in exchange for simple correctness.
"""

from django.core.files.base import ContentFile

from apps.core.fields import CURRENCY_CODE
from apps.core.models import RestaurantSettings

from . import pdf
from .models import Invoice, InvoiceSequence


def _local_year(now, restaurant):
    return now.astimezone(restaurant.zone).year


def ensure_sequence(now, restaurant=None):
    """Make sure the counter row of `now`'s year exists. Call outside any transaction."""
    restaurant = restaurant or RestaurantSettings.load()
    InvoiceSequence.objects.get_or_create(year=_local_year(now, restaurant))


def issue_invoice(order, payment, *, now, restaurant=None):
    """Issue the invoice of a fully paid order. Call inside the transaction that records the
    payment, after `ensure_sequence` and while holding the order's row lock."""
    existing = Invoice.objects.filter(order=order).first()
    if existing is not None:
        return existing

    restaurant = restaurant or RestaurantSettings.load()
    year = _local_year(now, restaurant)
    sequence = InvoiceSequence.objects.select_for_update().get(year=year)
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])

    invoice = Invoice.objects.create(
        order=order,
        invoice_number=f"INV-{year}-{sequence.last_number:06d}",
        total=order.total,
    )
    content = pdf.render_invoice(
        invoice=invoice,
        order=order,
        payment=payment,
        restaurant=restaurant,
        currency=CURRENCY_CODE,
    )
    invoice.pdf_file.save(f"{invoice.invoice_number}.pdf", ContentFile(content), save=True)
    return invoice