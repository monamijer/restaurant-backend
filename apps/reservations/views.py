from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import STAFF_ROLES, IsStaffRole
from apps.core.models import RestaurantSettings

from . import services
from .filters import ReservationFilter
from .models import Reservation
from .serializers import (
    AvailabilityQuerySerializer,
    AvailabilitySlotSerializer,
    ReservationCreateSerializer,
    ReservationSerializer,
)

STAFF_ACTIONS = {"confirm", "reject", "complete", "no_show"}


class ReservationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Customers see and manage their own reservations; staff see and decide on all of them."""

    serializer_class = ReservationSerializer
    filterset_class = ReservationFilter
    search_fields = ["customer__email", "customer__first_name", "customer__last_name"]
    ordering_fields = ["starts_at", "created_at"]
    ordering = ["starts_at"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Authentication has passed. Settle lapsed holds first so every response, and every
        # decision below, works on up-to-date statuses.
        services.expire_stale_pending()

    def get_permissions(self):
        if self.action in STAFF_ACTIONS:
            return [IsStaffRole()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = Reservation.objects.select_related("customer", "table")
        user = self.request.user
        if user.role in STAFF_ROLES:
            return queryset
        return queryset.filter(customer=user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["restaurant_settings"] = RestaurantSettings.load()
        return context

    def create(self, request, *args, **kwargs):
        context = self.get_serializer_context()
        serializer = ReservationCreateSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        reservation = services.create_reservation(
            customer=request.user,
            restaurant=context["restaurant_settings"],
            **serializer.validated_data,
        )
        return Response(
            ReservationSerializer(reservation, context=context).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"])
    def availability(self, request):
        context = self.get_serializer_context()
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        slots = services.get_availability(
            restaurant=context["restaurant_settings"],
            day=params["date"],
            party_size=params["party_size"],
            duration_minutes=params["duration_minutes"],
        )
        return Response(
            {
                "date": params["date"].isoformat(),
                "party_size": params["party_size"],
                "duration_minutes": params["duration_minutes"],
                "slots": AvailabilitySlotSerializer(slots, many=True).data,
            }
        )

    def _respond_with(self, service, **kwargs):
        reservation = self.get_object()  # 404 for a customer asking about someone else's
        updated = service(reservation.pk, **kwargs)
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._respond_with(services.confirm_reservation)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._respond_with(services.reject_reservation)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._respond_with(services.cancel_reservation, actor=request.user)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._respond_with(services.complete_reservation)

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        return self._respond_with(services.mark_no_show)