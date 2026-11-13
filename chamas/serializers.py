from rest_framework import serializers

from common.validators import validate_phone

from .models import Group

SUPPORTED_CURRENCIES = ["KES"]  # add more when the ledger supports them


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = [
            "id", "name", "slug", "group_type", "status", "description",
            "registration_number", "email", "phone_number", "country", "currency",
            "county", "town", "physical_address", "date_created",
        ]
        read_only_fields = ["id", "slug", "status", "date_created"]
        extra_kwargs = {
            "name": {"min_length": 3},
            "phone_number": {"validators": [validate_phone]},
        }

    def validate_currency(self, value):
        if value not in SUPPORTED_CURRENCIES:
            raise serializers.ValidationError(f"Supported currencies: {', '.join(SUPPORTED_CURRENCIES)}.")
        return value

    def validate_registration_number(self, value):
        if value and Group.objects.filter(registration_number=value).exists():
            raise serializers.ValidationError("A group with this registration number already exists.")
        return value