from django.core.management.base import BaseCommand

from apps.reservations import services


class Command(BaseCommand):
    help = "Turn pending reservation requests whose hold has lapsed into 'expired'."

    def handle(self, *args, **options):
        count = services.expire_stale_pending()
        self.stdout.write(f"Expired {count} reservation request(s).")