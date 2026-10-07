from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/stats/", views.DashboardStatsView.as_view(), name="dashboard-stats"),
    path("reports/revenue/", views.RevenueReport.as_view(), name="report-revenue"),
    path("reports/order-volume/", views.OrderVolumeReport.as_view(), name="report-order-volume"),
    path("reports/top-items/", views.TopItemsReport.as_view(), name="report-top-items"),
    path("reports/peak-hours/", views.PeakHoursReport.as_view(), name="report-peak-hours"),
    path(
        "reports/table-utilization/",
        views.TableUtilizationReport.as_view(),
        name="report-table-utilization",
    ),
    path("reports/payments/", views.PaymentsReport.as_view(), name="report-payments"),
]