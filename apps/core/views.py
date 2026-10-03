from rest_framework import generics
from rest_framework.permissions import SAFE_METHODS, AllowAny

from apps.accounts.permissions import IsAdminRole

from .models import RestaurantSettings
from .serializers import RestaurantSettingsSerializer


class RestaurantSettingsView(generics.RetrieveUpdateAPIView):
    """Singleton resource: public to read (hours, tax), admin-only to change."""

    serializer_class = RestaurantSettingsSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAdminRole()]

    def get_object(self):
        return RestaurantSettings.load()