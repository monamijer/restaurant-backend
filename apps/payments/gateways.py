"""Payment gateway abstraction.

The application only ever talks to a gateway through `charge()`. Replacing the simulated
gateway with a real provider means writing one class with the same method and pointing the
PAYMENT_GATEWAY setting at it. No card number ever reaches this application: the client
sends an opaque token produced by the provider.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class ChargeResult:
    approved: bool


class SimulatedGateway:
    """Stand-in for a card or mobile-money provider.

    The decision is made here, on the server, from the token alone: 'tok_declined' is refused
    and any other token is approved. It must be enabled explicitly outside development."""

    DECLINED_TOKEN = "tok_declined"

    def __init__(self):
        if not settings.ALLOW_SIMULATED_PAYMENTS:
            raise ImproperlyConfigured(
                "The simulated payment gateway is disabled. Configure a real gateway or "
                "set ALLOW_SIMULATED_PAYMENTS=True for a demo."
            )

    def charge(self, *, method, amount, token, reference):
        return ChargeResult(approved=token != self.DECLINED_TOKEN)


def get_gateway():
    return import_string(settings.PAYMENT_GATEWAY)()