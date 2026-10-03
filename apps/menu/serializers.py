from rest_framework import serializers

from apps.core.validators import validate_uploaded_image

from .models import Category, MenuItem

MAX_ALLERGENS = 20
MAX_ALLERGEN_LENGTH = 40


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "image", "display_order", "created_at", "updated_at")
        read_only_fields = ("slug", "created_at", "updated_at")

    def validate_image(self, value):
        return validate_uploaded_image(value)


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = MenuItem
        fields = (
            "id",
            "category",
            "category_name",
            "name",
            "slug",
            "description",
            "price",
            "image",
            "is_available",
            "preparation_time",
            "is_featured",
            "allergens",
            "calories",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("slug", "created_at", "updated_at")

    def validate_image(self, value):
        return validate_uploaded_image(value)

    def validate_allergens(self, value):
        if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
            raise serializers.ValidationError("Allergens must be a list of strings.")
        # dict.fromkeys removes duplicates while keeping the original order.
        cleaned = list(dict.fromkeys(entry.strip().lower() for entry in value if entry.strip()))
        if len(cleaned) > MAX_ALLERGENS:
            raise serializers.ValidationError(f"At most {MAX_ALLERGENS} allergens are allowed.")
        if any(len(entry) > MAX_ALLERGEN_LENGTH for entry in cleaned):
            raise serializers.ValidationError(
                f"Each allergen must be {MAX_ALLERGEN_LENGTH} characters or fewer."
            )
        return cleaned


class AvailabilitySerializer(serializers.Serializer):
    is_available = serializers.BooleanField()