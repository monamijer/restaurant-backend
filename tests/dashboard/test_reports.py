from datetime import timedelta
from decimal import Decimal

import pytest

from apps.core.models import RestaurantSettings
from apps.menu.models import MenuItem
from apps.orders.models import OrderType
from apps.payments.models import Payment, PaymentMethod
from apps.reservations.models import Reservation, ReservationStatus
from tests.dashboard.conftest import at

BASE = "/api/reports/"

pytestmark = pytest.mark.django_db


def rows(response):
    return response.data["results"]


def csv_lines(response):
    return response.content.decode("utf-8-sig").splitlines()


class TestAccess:
    def test_staff_cannot_read_reports(self, as_user, staff_user):
        assert as_user(staff_user).get(f"{BASE}revenue/").status_code == 403

    def test_admins_can(self, as_user, admin_user):
        assert as_user(admin_user).get(f"{BASE}revenue/").status_code == 200


class TestRevenue:
    def test_revenue_by_day(self, as_user, admin_user, record_sale, dish):
        record_sale(at(2026, 9, 1), lines=[(dish, 2)])
        record_sale(at(2026, 9, 1, 19), lines=[(dish, 1)])
        record_sale(at(2026, 9, 3))

        response = as_user(admin_user).get(f"{BASE}revenue/", {"start": "2026-09-01", "end": "2026-09-03"})

        assert [(row["period"], row["revenue"], row["orders"]) for row in rows(response)] == [
            ("2026-09-01", "37.50", 2),
            ("2026-09-02", "0.00", 0),
            ("2026-09-03", "12.50", 1),
        ]
        assert rows(response)[0]["average_order_value"] == "18.75"

    def test_weekly_buckets_start_on_monday(self, as_user, admin_user, record_sale):
        record_sale(at(2026, 9, 7))  # Monday
        record_sale(at(2026, 9, 9))  # Wednesday of the same week
        record_sale(at(2026, 9, 15))  # Tuesday of the next week

        response = as_user(admin_user).get(
            f"{BASE}revenue/", {"start": "2026-09-07", "end": "2026-09-20", "group_by": "week"}
        )

        assert [(row["period"], row["revenue"]) for row in rows(response)] == [
            ("2026-09-07", "25.00"),
            ("2026-09-14", "12.50"),
        ]

    def test_monthly_buckets(self, as_user, admin_user, record_sale):
        record_sale(at(2026, 8, 30))
        record_sale(at(2026, 9, 2))

        response = as_user(admin_user).get(
            f"{BASE}revenue/", {"start": "2026-08-25", "end": "2026-09-05", "group_by": "month"}
        )

        assert [(row["period"], row["revenue"]) for row in rows(response)] == [
            ("2026-08-01", "12.50"),
            ("2026-09-01", "12.50"),
        ]

    def test_days_follow_the_restaurant_timezone(self, as_user, admin_user, record_sale):
        restaurant = RestaurantSettings.load()
        restaurant.timezone = "Africa/Bujumbura"  # UTC+2
        restaurant.save()
        record_sale(at(2026, 9, 10, 23, 30))  # 01:30 on the 11th, local time

        response = as_user(admin_user).get(f"{BASE}revenue/", {"start": "2026-09-10", "end": "2026-09-11"})

        assert [(row["period"], row["revenue"]) for row in rows(response)] == [
            ("2026-09-10", "0.00"),
            ("2026-09-11", "12.50"),
        ]


class TestOrdersAndDishes:
    def test_order_volume_by_type(self, as_user, admin_user, record_sale, table):
        record_sale(at(2026, 9, 1), order_type=OrderType.DINE_IN, table=table)
        record_sale(at(2026, 9, 1, 13))
        record_sale(at(2026, 9, 1, 14), order_type=OrderType.DELIVERY)

        response = as_user(admin_user).get(f"{BASE}order-volume/", {"start": "2026-09-01", "end": "2026-09-01"})

        assert rows(response)[0] == {
            "period": "2026-09-01",
            "total": 3,
            "dine_in": 1,
            "takeaway": 1,
            "delivery": 1,
            "cancelled": 0,
        }

    def test_top_items_respect_the_limit(self, as_user, admin_user, record_sale, dish, side):
        record_sale(at(2026, 9, 1), lines=[(dish, 3), (side, 1)])

        response = as_user(admin_user).get(
            f"{BASE}top-items/", {"start": "2026-09-01", "end": "2026-09-01", "limit": 1}
        )

        assert [(row["name"], row["quantity"]) for row in rows(response)] == [("Grilled fish", 3)]

    def test_peak_hours_cover_the_whole_day(self, as_user, admin_user, record_sale):
        record_sale(at(2026, 9, 1, 12, 10))
        record_sale(at(2026, 9, 1, 12, 50))
        record_sale(at(2026, 9, 1, 19, 5))

        response = as_user(admin_user).get(f"{BASE}peak-hours/", {"start": "2026-09-01", "end": "2026-09-01"})

        by_hour = {row["hour"]: row for row in rows(response)}
        assert len(by_hour) == 24
        assert by_hour[12]["orders"] == 2 and by_hour[12]["revenue"] == "25.00"
        assert by_hour[19]["orders"] == 1
        assert by_hour[3]["orders"] == 0


class TestTableUtilization:
    def test_booked_minutes_against_opening_minutes(
        self, as_user, admin_user, customer, table, record_sale
    ):
        def book(status, hour):
            starts_at = at(2026, 9, 10, hour)
            return Reservation.objects.create(
                customer=customer,
                table=table,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=2),
                party_size=2,
                status=status,
            )

        book(ReservationStatus.COMPLETED, 19)  # 120 minutes of the 780 open minutes
        book(ReservationStatus.REJECTED, 12)  # Not a real booking: ignored
        record_sale(at(2026, 9, 10, 20), order_type=OrderType.DINE_IN, table=table)

        response = as_user(admin_user).get(
            f"{BASE}table-utilization/", {"start": "2026-09-10", "end": "2026-09-10"}
        )

        row = rows(response)[0]
        assert (row["number"], row["reservations"], row["reserved_minutes"]) == (1, 1, 120)
        assert row["utilisation_percent"] == 15.4
        assert row["dine_in_orders"] == 1 and row["orders_value"] == "12.50"


class TestCsvExports:
    def test_a_report_can_be_downloaded_as_csv(self, as_user, admin_user, record_sale):
        record_sale(at(2026, 9, 1))

        response = as_user(admin_user).get(
            f"{BASE}revenue/", {"start": "2026-09-01", "end": "2026-09-01", "export": "csv"}
        )

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert 'filename="revenue-2026-09-01-2026-09-01.csv"' in response["Content-Disposition"]
        assert "no-store" in response["Cache-Control"]
        assert response.content.startswith("\ufeff".encode())
        assert csv_lines(response) == [
            "period,revenue,orders,average_order_value",
            "2026-09-01,12.50,1,12.50",
        ]

    def test_formula_like_dish_names_are_defused(
        self, as_user, admin_user, record_sale, dish
    ):
        sneaky = MenuItem.objects.create(
            category=dish.category, name="=HYPERLINK(\"http://evil.example\")", price=Decimal("1.00")
        )
        record_sale(at(2026, 9, 1), lines=[(sneaky, 1)])

        response = as_user(admin_user).get(
            f"{BASE}top-items/", {"start": "2026-09-01", "end": "2026-09-01", "export": "csv"}
        )

        assert "'=HYPERLINK" in csv_lines(response)[1]

    def test_the_payment_ledger_is_csv_only(self, as_user, admin_user, record_sale):
        record_sale(at(2026, 9, 1))
        params = {"start": "2026-09-01", "end": "2026-09-01"}

        as_json = as_user(admin_user).get(f"{BASE}payments/", params)
        as_csv = as_user(admin_user).get(f"{BASE}payments/", {**params, "export": "csv"})

        assert as_json.status_code == 400
        assert "export" in as_json.data["errors"]
        lines = csv_lines(as_csv)
        assert lines[0] == "reference,order,method,status,amount,created_at,paid_at"
        assert lines[1].startswith("PAY-") and ",paid,12.50," in lines[1]


class TestValidation:
    @pytest.mark.parametrize(
        "params",
        [{"group_by": "decade"}, {"limit": 0}, {"limit": 51}, {"export": "xlsx"}],
    )
    def test_bad_parameters_are_rejected(self, as_user, admin_user, params):
        response = as_user(admin_user).get(f"{BASE}top-items/", params)

        assert response.status_code == 400
        assert response.data["code"] == "VALIDATION_ERROR"

    def test_a_period_over_a_year_is_rejected(self, as_user, admin_user):
        response = as_user(admin_user).get(f"{BASE}revenue/", {"start": "2025-01-01", "end": "2026-09-01"})

        assert response.status_code == 400