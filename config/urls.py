"""Root URL configuration. One router exposes every resource under /api/."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.core.views import RestaurantSettingsView
from apps.menu.views import CategoryViewSet, MenuItemViewSet
from apps.notifications.views import NotificationViewSet
from apps.tables.views import TableViewSet
from apps.reservations.views import ReservationViewSet
from apps.queue_mgmt.views import QueueViewSet
from apps.orders.views import OrderViewSet

router = SimpleRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("menu-items", MenuItemViewSet, basename="menu-item")
router.register("tables", TableViewSet, basename="table")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("reservations", ReservationViewSet, basename="reservation")
router.register("queue", QueueViewSet, basename="queue")
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/settings/", RestaurantSettingsView.as_view(), name="restaurant-settings"),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    # Uploaded images are served by Django only in development.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)