from django.db import models

CURRENCY_CODE = "USD"
MONEY_MAX_DIGITS = 10
MONEY_DECIMAL_PLACES = 2


def money_field(**kwargs):
    """Decimal column for amounts. Money is never stored as a float."""
    return models.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, **kwargs
    )