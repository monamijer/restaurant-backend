import pytest


@pytest.fixture
def order(customer, make_order):
    """A pending order of 10.00 owned by the customer."""
    return make_order(customer)