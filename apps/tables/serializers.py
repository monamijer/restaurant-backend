from rest_framework import serializers

from .models import Table, TableStatus

MAX_TABLE_CAPACITY = 50


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ("id", "number", "capacity", "status", "location", "qr_code", "created_at", "updated_at")
        # Status only changes through the dedicated action, never through generic CRUD.
        read_only_fields = ("status", "qr_code", "created_at", "updated_at")
        extra_kwargs = {
            "number": {"min_value": 1},
            "capacity": {"min_value": 1, "max_value": MAX_TABLE_CAPACITY},
        }


class TableStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TableStatus.choices)