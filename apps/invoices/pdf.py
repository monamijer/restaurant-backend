"""Invoice PDF rendering with ReportLab: data in, PDF bytes out, no database access."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PAGE_MARGIN = 18 * mm
HEADER_BACKGROUND = colors.HexColor("#1f3d2b")
RULE_COLOR = colors.HexColor("#c9c2b0")
ITEM_COLUMNS = (85 * mm, 20 * mm, 30 * mm, 30 * mm)
TOTAL_COLUMNS = (135 * mm, 30 * mm)
GUEST_LABEL = "Guest"


def _text(value):
    """Paragraphs read a small XML markup: user text must be escaped, never trusted."""
    return escape(str(value))


def _items_table(order, styles, currency):
    rows = [["Item", "Qty", f"Unit price ({currency})", f"Amount ({currency})"]]
    for item in order.items.order_by("pk"):
        rows.append(
            [
                Paragraph(_text(item.item_name), styles["Normal"]),
                str(item.quantity),
                str(item.unit_price),
                str(item.subtotal),
            ]
        )
    table = Table(rows, colWidths=ITEM_COLUMNS, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BACKGROUND),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE_COLOR),
            ]
        )
    )
    return table


def _totals_table(order, currency):
    rows = [
        ["Subtotal", f"{order.subtotal} {currency}"],
        [f"Tax ({order.tax_rate}%)", f"{order.tax_amount} {currency}"],
        ["Total", f"{order.total} {currency}"],
    ]
    table = Table(rows, colWidths=TOTAL_COLUMNS)
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.75, HEADER_BACKGROUND),
            ]
        )
    )
    return table


def render_invoice(*, invoice, order, payment, restaurant, currency):
    styles = getSampleStyleSheet()
    zone = restaurant.zone
    issued = invoice.issued_at.astimezone(zone)
    paid = payment.paid_at.astimezone(zone)
    customer = order.customer.full_name if order.customer_id else GUEST_LABEL
    where = f", table {order.table.number}" if order.table_id else ""

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title=f"Invoice {invoice.invoice_number}",
        author=restaurant.name,
    )
    story = [
        Paragraph(_text(restaurant.name), styles["Title"]),
        Paragraph(f"Invoice {_text(invoice.invoice_number)}", styles["Heading2"]),
        Paragraph(f"Issued: {issued:%Y-%m-%d %H:%M}", styles["Normal"]),
        Paragraph(
            f"Order #{order.pk} ({_text(order.get_order_type_display())}{where})", styles["Normal"]
        ),
        Paragraph(f"Customer: {_text(customer)}", styles["Normal"]),
        Spacer(1, 8 * mm),
        _items_table(order, styles, currency),
        Spacer(1, 6 * mm),
        _totals_table(order, currency),
        Spacer(1, 8 * mm),
        Paragraph(
            f"Paid by {_text(payment.get_method_display())} on {paid:%Y-%m-%d %H:%M} "
            f"(reference {_text(payment.reference)}).",
            styles["Normal"],
        ),
    ]
    document.build(story)
    return buffer.getvalue()