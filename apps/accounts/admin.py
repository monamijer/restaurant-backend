from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "last_name", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("password", "last_login", "created_at", "updated_at")
    exclude = ("groups", "user_permissions")

    def has_add_permission(self, request):
        # Accounts are created through the API or `createsuperuser`, never with a blank password.
        return False
