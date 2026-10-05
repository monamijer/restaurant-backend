from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.permissions import STAFF_ROLES, IsStaffRole

from . import services
from .filters import PaymentFilter
from .models import Payment
from .serializers import PaymentCreateSerializer, PaymentSerializer


class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Customers pay for and follow their own orders; staff confirm cash and see everything."""

    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter
    search_fields = ["reference"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]
    throttle_scope = "payments"

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == "create":
            throttles.append(ScopedRateThrottle())  # Slows down card-testing attacks.
        return throttles

    def get_queryset(self):
        queryset = Payment.objects.select_related("order")
        user = self.request.user
        if user.role in STAFF_ROLES:
            return queryset
        return queryset.filter(order__customer=user)

    def create(self, request, *args, **kwargs):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.start_payment(actor=request.user, **serializer.validated_data)
        # A declined card is a recorded payment with status "failed", not an HTTP error.
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[IsStaffRole])
    def confirm(self, request, pk=None):
        payment = self.get_object()
        updated = services.confirm_cash_payment(payment.pk)
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        payment = self.get_object()  # 404 for a customer asking about someone else's payment
        updated = services.cancel_payment(payment.pk, actor=request.user)
        return Response(self.get_serializer(updated).data)