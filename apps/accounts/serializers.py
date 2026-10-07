"""Serializers for authentication, the current-user profile and account management."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from . import password_reset

from .models import User

MAX_EMAIL_LENGTH = 254
MONEY_DIGITS = 12


def check_password_strength(password, user, field="password"):
    """Run Django's password validators against the candidate user; errors keyed by `field`."""
    try:
        validate_password(password, user=user)
    except DjangoValidationError as error:
        raise serializers.ValidationError({field: list(error.messages)})


def unique_email(value):
    email = User.objects.normalize_email(value)
    if User.objects.filter(email__iexact=email).exists():
        raise serializers.ValidationError("A user with this email already exists.")
    return email


class UserSerializer(serializers.ModelSerializer):
    """Public profile. Identity and role are read-only: no mass assignment."""

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "phone", "address", "role", "created_at")
        read_only_fields = ("id", "email", "role", "created_at")


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ("email", "password", "first_name", "last_name", "phone", "address")

    def validate_email(self, value):
        return unique_email(value)

    def validate(self, attrs):
        candidate = User(
            email=attrs["email"], first_name=attrs["first_name"], last_name=attrs["last_name"]
        )
        check_password_strength(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        # 'role' is not a field here, so public registration can only create clients.
        return User.objects.create_user(**validated_data)

    def to_representation(self, instance):
        return UserSerializer(instance, context=self.context).data


class LoginSerializer(TokenObtainPairSerializer):
    """Standard token pair plus the profile, saving the client a second round trip."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({"old_password": ["The current password is incorrect."]})
        check_password_strength(attrs["new_password"], user, field="new_password")
        return attrs


# --- Account management (staff and administrators) -------------------------------------
class UserAdminSerializer(serializers.ModelSerializer):
    """Read model for the account pages, with customer statistics added by the queryset."""

    orders_count = serializers.IntegerField(read_only=True)
    total_spent = serializers.DecimalField(max_digits=MONEY_DIGITS, decimal_places=2, read_only=True)
    last_order_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "address",
            "role",
            "is_active",
            "last_login",
            "created_at",
            "orders_count",
            "total_spent",
            "last_order_at",
        )
        read_only_fields = fields


class UserCreateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ("email", "password", "first_name", "last_name", "phone", "address", "role")

    def validate_email(self, value):
        return unique_email(value)

    def validate(self, attrs):
        candidate = User(
            email=attrs["email"], first_name=attrs["first_name"], last_name=attrs["last_name"]
        )
        check_password_strength(attrs["password"], candidate)
        return attrs


class UserUpdateSerializer(serializers.ModelSerializer):
    """Identity (email) and password are deliberately not editable here."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone", "address", "role", "is_active")


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        check_password_strength(attrs["password"], self.context["target"])
        return attrs

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=MAX_EMAIL_LENGTH)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=MAX_EMAIL_LENGTH)
    token = serializers.CharField(max_length=MAX_EMAIL_LENGTH)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = password_reset.resolve_user(attrs["uid"], attrs["token"])
        check_password_strength(attrs["new_password"], user, field="new_password")
        attrs["user"] = user
        return attrs