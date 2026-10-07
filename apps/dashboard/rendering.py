"""Turning metrics into HTTP bodies: money as strings, and safe CSV downloads."""

import csv
from decimal import Decimal

from django.http import HttpResponse

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
UTF8_BOM = "\ufeff"  # Lets Excel open accented text correctly.


def money_as_strings(value):
    """DRF would encode a bare Decimal as a float; money must stay an exact string."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: money_as_strings(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [money_as_strings(item) for item in value]
    return value


def safe_cell(value):
    """Defuse spreadsheet formula injection: a cell that starts like a formula becomes text."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response.write(UTF8_BOM)
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return response