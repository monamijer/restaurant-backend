"""Table QR codes: a signed link proving that someone is physically at a table.

A code encodes `FRONTEND_URL/scan?t=<token>`. The token is signed with the server secret and
carries the table's `qr_version`, so printed codes cannot be forged and can all be revoked by
regenerating a table's code. Nothing is stored: images are rendered on demand for
administrators and never written to a public folder."""

from io import BytesIO

import qrcode
from django.conf import settings
from django.core import signing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from rest_framework.exceptions import ValidationError

from .models import Table

SIGNING_SALT = "table-qr"
INVALID_CODE = "This table QR code is invalid or has been replaced."
QR_BOX_SIZE = 10
QR_BORDER = 4
SHEET_COLUMNS = 2
SHEET_ROWS = 3
SHEET_PADDING = 40 * mm
TITLE_FONT_SIZE = 20
TEXT_FONT_SIZE = 11


def make_token(table):
    return signing.dumps({"table": table.pk, "version": table.qr_version}, salt=SIGNING_SALT)


def resolve_token(token, field="table_token"):
    """The table a valid, current token points to. Any defect gives the same error."""
    try:
        data = signing.loads(token, salt=SIGNING_SALT)  # No max age: codes are printed.
        return Table.objects.get(pk=data["table"], qr_version=data["version"])
    except (signing.BadSignature, KeyError, TypeError, Table.DoesNotExist):
        raise ValidationError({field: [INVALID_CODE]})


def scan_url(table):
    return f"{settings.FRONTEND_URL}/scan?t={make_token(table)}"


def render_png(table):
    image = qrcode.make(
        scan_url(table),
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=QR_BOX_SIZE,
        border=QR_BORDER,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_sheet(tables, restaurant_name):
    """An A4 PDF, six codes per page, ready to print and cut out."""
    buffer = BytesIO()
    page_width, page_height = A4
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"{restaurant_name}: table QR codes")
    cell_width, cell_height = page_width / SHEET_COLUMNS, page_height / SHEET_ROWS
    code_size = min(cell_width, cell_height) - SHEET_PADDING
    per_page = SHEET_COLUMNS * SHEET_ROWS

    for index, table in enumerate(tables):
        slot = index % per_page
        if index and slot == 0:
            pdf.showPage()
        centre = (slot % SHEET_COLUMNS) * cell_width + cell_width / 2
        top = page_height - (slot // SHEET_COLUMNS) * cell_height

        pdf.setFont("Helvetica-Bold", TITLE_FONT_SIZE)
        pdf.drawCentredString(centre, top - 14 * mm, f"Table {table.number}")
        picture = ImageReader(BytesIO(render_png(table)))
        pdf.drawImage(picture, centre - code_size / 2, top - 20 * mm - code_size, code_size, code_size)
        pdf.setFont("Helvetica", TEXT_FONT_SIZE)
        pdf.drawCentredString(centre, top - 26 * mm - code_size, "Scannez pour commander / Scan to order")
        if table.location:
            pdf.drawCentredString(centre, top - 32 * mm - code_size, table.location)
    pdf.save()
    return buffer.getvalue()