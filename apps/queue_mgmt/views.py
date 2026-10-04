from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import STAFF_ROLES, IsStaffRole
from apps.core.models import RestaurantSettings

from . import services
from .filters import QueueTicketFilter
from .models import QueueTicket
from .serializers import QueueJoinSerializer, QueueTicketSerializer

STAFF_ACTIONS = {"call", "call_next", "seat", "no_show"}
PUBLIC_ACTIONS = {"summary"}


class QueueViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Customers see and manage their own tickets; staff run the whole queue."""

    serializer_class = QueueTicketSerializer
    filterset_class = QueueTicketFilter
    search_fields = ["customer_name", "phone"]
    ordering_fields = ["pk", "created_at"]
    ordering = ["pk"]

    def get_permissions(self):
        if self.action in PUBLIC_ACTIONS:
            return [AllowAny()]
        if self.action in STAFF_ACTIONS:
            return [IsStaffRole()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = QueueTicket.objects.select_related("customer")
        user = self.request.user
        if user.role in STAFF_ROLES:
            return queryset
        return queryset.filter(customer=user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["restaurant_settings"] = RestaurantSettings.load()
        context["positions"] = services.waiting_positions()
        return context

    def create(self, request, *args, **kwargs):
        serializer = QueueJoinSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        ticket = services.join_queue(**serializer.validated_data)
        return Response(self.get_serializer(ticket).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Public: how long a party arriving now should expect to wait."""
        restaurant = RestaurantSettings.load()
        waiting = len(services.waiting_positions())
        return Response(
            {
                "waiting": waiting,
                "estimated_wait_minutes": services.estimate_wait_minutes(waiting + 1, restaurant),
            }
        )

    @action(detail=False, methods=["post"], url_path="call-next")
    def call_next(self, request):
        ticket = services.call_next()
        return Response(self.get_serializer(ticket).data)

    def _respond_with(self, service, **kwargs):
        ticket = self.get_object()  # 404 for a customer asking about someone else's ticket
        updated = service(ticket.pk, **kwargs)
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["post"])
    def call(self, request, pk=None):
        return self._respond_with(services.call_ticket)

    @action(detail=True, methods=["post"])
    def seat(self, request, pk=None):
        return self._respond_with(services.seat_ticket)

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        return self._respond_with(services.mark_no_show)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._respond_with(services.cancel_ticket, actor=request.user)