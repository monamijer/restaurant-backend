from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole, IsStaffRole
from apps.core.models import RestaurantSettings

from . import metrics
from .rendering import csv_response, json_ready
from .serializers import PeriodQuerySerializer


def read_query(request):
    """Validate the query string and return (restaurant settings, validated parameters)."""
    restaurant = RestaurantSettings.load()
    serializer = PeriodQuerySerializer(
        data=request.query_params, context={"restaurant_settings": restaurant}
    )
    serializer.is_valid(raise_exception=True)
    return restaurant, serializer.validated_data


class DashboardStatsView(APIView):
    """Operations overview for staff and administrators."""

    permission_classes = [IsStaffRole]

    def get(self, request):
        restaurant, params = read_query(request)
        return Response(json_ready(metrics.build_stats(restaurant, params["period"])))


class ReportView(APIView):
    """A report is a list of rows, served as JSON or, with ?export=csv, as a download."""

    permission_classes = [IsAdminRole]
    name = ""  # Used in the CSV file name.
    header = ()  # CSV columns, in order; also the keys read from each row.
    csv_only = False

    def rows(self, restaurant, period, params):
        raise NotImplementedError

    def get(self, request):
        restaurant, params = read_query(request)
        period = params["period"]
        wants_csv = params.get("export") == "csv"
        if self.csv_only and not wants_csv:
            raise ValidationError({"export": ["This report is only available as CSV (export=csv)."]})

        rows = self.rows(restaurant, period, params)
        if wants_csv:
            filename = f"{self.name}-{period.start_day}-{period.end_day}.csv"
            return csv_response(filename, self.header, ([row[col] for col in self.header] for row in rows))
        return Response(
            json_ready({"start": period.start_day, "end": period.end_day, "results": rows})
        )


class RevenueReport(ReportView):
    name = "revenue"
    header = ("period", "revenue", "orders", "average_order_value")

    def rows(self, restaurant, period, params):
        return metrics.revenue_series(period, params["group_by"])


class OrderVolumeReport(ReportView):
    name = "order-volume"
    header = ("period", "total", "dine_in", "takeaway", "delivery", "cancelled")

    def rows(self, restaurant, period, params):
        return metrics.order_volume_series(period, params["group_by"])


class TopItemsReport(ReportView):
    name = "top-items"
    header = ("menu_item", "name", "quantity", "revenue")

    def rows(self, restaurant, period, params):
        return metrics.top_items(period, params["limit"])


class PeakHoursReport(ReportView):
    name = "peak-hours"
    header = ("hour", "orders", "revenue")

    def rows(self, restaurant, period, params):
        return metrics.peak_hours(period)


class TableUtilizationReport(ReportView):
    name = "table-utilization"
    header = (
        "number",
        "capacity",
        "reservations",
        "reserved_minutes",
        "utilisation_percent",
        "dine_in_orders",
        "orders_value",
    )

    def rows(self, restaurant, period, params):
        return metrics.table_utilization(period, restaurant)


class PaymentsReport(ReportView):
    name = "payments"
    header = ("reference", "order", "method", "status", "amount", "created_at", "paid_at")
    csv_only = True

    def rows(self, restaurant, period, params):
        return metrics.payments_listing(period)