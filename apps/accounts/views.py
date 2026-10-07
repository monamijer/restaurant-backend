"""Authentication endpoints. Views stay thin: validation lives in serializers."""

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import status

from apps.accounts import password_reset

from . import services
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # A stale Authorization header must not break registration.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch", "head", "options"]  # Partial updates only.

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """Change the caller's own password and get fresh tokens; other sessions are signed out."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"  # The current password is being guessed otherwise.

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tokens = services.change_own_password(
            request.user, serializer.validated_data["new_password"]
        )
        return Response(tokens)
class PasswordResetRequestView(APIView):
    """Ask for a reset link. The answer is the same whether or not the address is known."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password_reset.request_reset(serializer.validated_data["email"])
        return Response({"detail": "If an account exists for this address, a link has been sent."})


class PasswordResetConfirmView(APIView):
    """Set a new password with the link received by e-mail."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        services.set_user_password(user.pk, serializer.validated_data["new_password"])
        return Response(status=status.HTTP_204_NO_CONTENT)