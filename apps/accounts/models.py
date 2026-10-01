"""Custom user: email is the identity, role is the authorization axis."""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models

PHONE_VALIDATOR = RegexValidator(
    regex=r"^\+?[0-9 ()-]{7,20}$",
    message="Enter a valid phone number.",
)


class Role(models.TextChoices):
    CLIENT = "client", "Client"
    STAFF = "staff", "Staff"
    ADMIN = "admin", "Administrator"


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        """Emails are case-insensitive identities: store them trimmed and lowercased."""
        return (email or "").strip().lower()

    def get_by_natural_key(self, email):
        return self.get(email=self.normalize_email(email))

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.CLIENT)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        if not password:
            raise ValueError("A superuser must have a password.")
        extra_fields["role"] = Role.ADMIN
        extra_fields["is_superuser"] = True
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=254, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, validators=[PHONE_VALIDATOR])
    address = models.TextField(blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CLIENT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["role"])]

    @property
    def is_staff(self):
        """Django-admin access only. Unrelated to the restaurant 'staff' role."""
        return self.is_superuser

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.email# Create your models here.
