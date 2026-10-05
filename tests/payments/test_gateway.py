from decimal import Decimal

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.payments.gateways import SimulatedGateway, get_gateway


def charge(gateway, token):
    return gateway.charge(
        method="card", amount=Decimal("10.00"), token=token, reference="PAY-TEST"
    )


def test_the_simulated_gateway_declines_only_the_declined_token():
    gateway = SimulatedGateway()

    assert charge(gateway, "tok_visa").approved is True
    assert charge(gateway, SimulatedGateway.DECLINED_TOKEN).approved is False


def test_the_configured_gateway_is_loaded():
    assert isinstance(get_gateway(), SimulatedGateway)


def test_the_simulated_gateway_refuses_to_run_unless_enabled(settings):
    settings.ALLOW_SIMULATED_PAYMENTS = False

    with pytest.raises(ImproperlyConfigured):
        get_gateway()