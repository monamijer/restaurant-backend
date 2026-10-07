from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.models import OrderStatus
from apps.payments.models import Payment, PaymentMethod, PaymentStatus
from apps.queue_mgmt.models import QueueTicket
from apps.tables.models import Table, TableStatus
from tests.dashboard.conftest import at

URL = "/api/dashboard/stats/"
SEPTEMBER = {"start": "2026-09-01", "end": "2026-09-30"}

pytestmark = pytest.mark.django_db


@pytest.fixture
def september_sales(record_sale, dish, side):
    record_sale(at(2026, 9, 5), lines=[(dish, 2)])  # 25.00
    record_sale(at(2026, 9, 6, 19), lines=[(dish, 1), (side, 1)])  # 18.50
    record_sale(at(2026, 9, 7, 19, 30), status=OrderStatus.CANCELLED, paid=False)  # not revenue
    record_sale(at(2026, 8, 20, 10))  # 12.50, in the previous period


class TestKpis:
    def test_revenue_orders_and_average_with_their_previous_period(
        self, as_user, staff_user, september_sales
    ):
        stats = as_user(staff_user).get(URL, SEPTEMBER).data

        assert stats["kpis"]["revenue"] == {"value": "43.50", "previous": "12.50", "change_percent": 248.0}
        assert stats["kpis"]["orders"] == {"value": 2, "previous": 1, "change_percent": 100.0}
        assert stats["kpis"]["average_order_value"]["value"] == "21.75"
        assert stats["kpis"]["average_order_value"]["change_percent"] == 74.0

    def test_the_change_is_null_when_there_is_nothing_to_compare(
        self, as_user, staff_user, record_sale
    ):
        record_sale(at(2026, 9, 5))

        kpi = as_user(staff_user).get(URL, SEPTEMBER).data["kpis"]["revenue"]

        assert kpi["previous"] == "0.00"
        assert kpi["change_percent"] is None

    def test_new_customers_count_only_clients_in_the_period(
        self, as_user, staff_user, create_user
    ):
        inside = create_user(email="inside@example.com")
        outside = create_user(email="outside@example.com")
        User.objects.filter(pk=inside.pk).update(created_at=at(2026, 9, 10))
        User.objects.filter(pk=outside.pk).update(created_at=at(2026, 8, 15))

        kpi = as_user(staff_user).get(URL, SEPTEMBER).data["kpis"]["new_customers"]

        assert kpi["value"] == 1
        assert kpi["previous"] == 1
        assert kpi["change_percent"] == 0.0

    def test_money_is_serialised_as_exact_strings(self, as_user, staff_user, september_sales):
        stats = as_user(staff_user).get(URL, SEPTEMBER).data

        assert isinstance(stats["kpis"]["revenue"]["value"], str)
        assert isinstance(stats["revenue_over_time"][4]["revenue"], str)


class TestSeries:
    def test_revenue_over_time_has_one_row_per_day_including_empty_ones(
        self, as_user, staff_user, september_sales
    ):
        series = as_user(staff_user).get(URL, SEPTEMBER).data["revenue_over_time"]

        assert len(series) == 30
        assert series[0]["period"] == "2026-09-01" and series[0]["revenue"] == "0.00"
        assert series[4]["period"] == "2026-09-05" and series[4]["revenue"] == "25.00"
        assert series[5]["revenue"] == "18.50"

    def test_top_items_exclude_cancelled_orders_and_sort_by_quantity(
        self, as_user, staff_user, september_sales
    ):
        top = as_user(staff_user).get(URL, SEPTEMBER).data["top_items"]

        assert [(item["name"], item["quantity"]) for item in top] == [("Grilled fish", 3), ("Fries", 1)]
        assert top[0]["revenue"] == "37.50"

    def test_orders_over_time_separates_types_and_cancellations(
        self, as_user, staff_user, september_sales
    ):
        series = as_user(staff_user).get(URL, SEPTEMBER).data["orders_over_time"]

        assert series[4]["total"] == 1 and series[4]["takeaway"] == 1
        assert series[6]["total"] == 0 and series[6]["cancelled"] == 1


class TestLiveSnapshot:
    def test_it_reports_tables_queue_orders_and_payments_right_now(
        self, as_user, staff_user, make_order, customer
    ):
        Table.objects.create(number=1, capacity=2, status=TableStatus.OCCUPIED)
        Table.objects.create(number=2, capacity=2)
        Table.objects.create(number=3, capacity=2)
        QueueTicket.objects.create(customer_name="Walk-in", party_size=2)
        pending_order = make_order(customer)
        make_order(customer, status=OrderStatus.COMPLETED)
        Payment.objects.create(order=pending_order, method=PaymentMethod.CASH, amount=pending_order.total)

        today = as_user(staff_user).get(URL).data["today"]

        assert today["tables"] == {
            "total": 3,
            "available": 2,
            "occupied": 1,
            "reserved": 0,
            "cleaning": 0,
            "occupancy_percent": 33.3,
        }
        assert today["queue_waiting"] == 1
        assert today["orders_in_progress"] == 1
        assert today["pending_payments"] == 1


class TestActivityAndPeriod:
    def test_recent_activity_is_newest_first_and_bounded(self, as_user, staff_user, record_sale):
        for day in range(1, 8):
            record_sale(at(2026, 9, day))

        activity = as_user(staff_user).get(URL, SEPTEMBER).data["recent_activity"]

        moments = [event["at"] for event in activity]
        assert len(activity) == 10
        assert moments == sorted(moments, reverse=True)
        assert {event["type"] for event in activity} <= {"order", "payment", "reservation"}

    def test_the_default_period_is_the_last_thirty_days(self, as_user, staff_user):
        stats = as_user(staff_user).get(URL).data

        assert stats["period"]["days"] == 30

    def test_an_end_before_the_start_is_rejected(self, as_user, staff_user):
        response = as_user(staff_user).get(URL, {"start": "2026-09-30", "end": "2026-09-01"})

        assert response.status_code == 400
        assert "start" in response.data["errors"]

    def test_a_period_over_a_year_is_rejected(self, as_user, staff_user):
        response = as_user(staff_user).get(URL, {"start": "2025-01-01", "end": "2026-09-01"})

        assert response.status_code == 400
        assert "end" in response.data["errors"]

    @pytest.mark.parametrize("params", [{"start": "not-a-date"}, {"end": "0001-01-01"}])
    def test_nonsense_dates_are_rejected_cleanly(self, as_user, staff_user, params):
        response = as_user(staff_user).get(URL, params)

        assert response.status_code == 400

    def test_customers_cannot_open_the_dashboard(self, as_user, customer):
        assert as_user(customer).get(URL).status_code == 403


def test_the_dashboard_agrees_with_the_seeded_ledger(as_user, staff_user):
    call_command("seed_demo", "--force", "--days", "3", "--orders-per-day", "3", "--no-images", stdout=StringIO())
    ledger = Payment.objects.filter(status=PaymentStatus.PAID).aggregate(total=Sum("amount"))["total"]

    stats = as_user(staff_user).get(URL).data

    assert Decimal(stats["kpis"]["revenue"]["value"]) == ledger
    assert stats["today"]["tables"]["total"] == 10
    assert len(stats["recent_activity"]) == 10
    assert timezone.now() - timedelta(days=31) < timezone.now()