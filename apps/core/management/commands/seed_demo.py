from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.core.seeding.builder import DemoBuilder, wipe
from apps.core.seeding.people import DEMO_DOMAIN, DEMO_PASSWORD, create_people, demo_accounts

DEFAULT_DAYS = 30
DEFAULT_ORDERS_PER_DAY = 5
DEFAULT_RANDOM_SEED = 2026


class Command(BaseCommand):
    help = (
        "Load a believable demo restaurant: accounts, menu, tables, 30 days of history, "
        "reservations, a queue and live orders. Safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete ALL restaurant data and the demo accounts first, then rebuild.",
        )
        parser.add_argument(
            "--force", action="store_true", help="Allow running when DEBUG is off."
        )
        parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
        parser.add_argument("--orders-per-day", type=int, default=DEFAULT_ORDERS_PER_DAY)
        parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
        parser.add_argument("--no-images", action="store_true", help="Skip placeholder pictures.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to create accounts with a well-known password while DEBUG is off. "
                "Use --force if you really mean it."
            )
        if options["days"] < 1 or options["orders_per_day"] < 1:
            raise CommandError("--days and --orders-per-day must be at least 1.")

        if options["reset"]:
            wipe()
            self.stdout.write("Existing restaurant data removed.")
        elif demo_accounts().exists():
            self.stdout.write("Demo data is already present. Use --reset to rebuild it.")
            return

        people = create_people()
        builder = DemoBuilder(
            people,
            seed=options["seed"],
            with_images=not options["no_images"],
            log=self.stdout.write,
        )
        builder.build(days=options["days"], per_day=options["orders_per_day"])
        self._summary(people)

    def _summary(self, people):
        from apps.invoices.models import Invoice
        from apps.menu.models import MenuItem
        from apps.orders.models import Order
        from apps.queue_mgmt.models import QueueTicket
        from apps.reservations.models import Reservation

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(
            f"  {MenuItem.objects.count()} dishes, {Order.objects.count()} orders, "
            f"{Invoice.objects.count()} invoices, {Reservation.objects.count()} reservations, "
            f"{QueueTicket.objects.count()} queue tickets"
        )
        self.stdout.write(f"  Accounts (password for all: {DEMO_PASSWORD})")
        for role in (Role.ADMIN, Role.STAFF, Role.CLIENT):
            emails = ", ".join(user.email for user in people[role])
            self.stdout.write(f"    {role}: {emails}")
        self.stdout.write(f"  Demo accounts use the @{DEMO_DOMAIN} domain.")