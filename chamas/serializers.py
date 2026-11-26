from datetime import UTC

from rest_framework import serializers

from accounts.models import Role, User
from common.validators import validate_phone

from .models import Group, Membership

SUPPORTED_CURRENCIES = ["KES"]

# add more when the ledger supports them
class MembershipSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = Membership
        fields = ["member_number", "role", "status", "joined_at"]


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "first_name", "last_name", "email")
        read_only_fields = fields


class MemberRoleSerializer(serializers.ModelSerializer):
    code = serializers.CharField(read_only=True)

    class Meta:
        model = Role
        fields = ("code", "name")
        read_only_fields = fields


class GroupMemberSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)
    role = MemberRoleSerializer(source="group_role", read_only=True, allow_null=True)
    joined_at = serializers.DateTimeField(default_timezone=UTC, read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "member_number", "user", "role", "status", "joined_at")
        read_only_fields = fields


class GroupMembersQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    status = serializers.ChoiceField(choices=Membership.Status.choices, required=False)
    role = serializers.CharField(required=False, max_length=200)


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

    def validate_currency(self, value) -> str:
        if value not in SUPPORTED_CURRENCIES:
            raise serializers.ValidationError(f"Supported currencies: {', '.join(SUPPORTED_CURRENCIES)}.")
        return value

    def validate_registration_number(self, value) -> str:
        if value and Group.objects.filter(registration_number=value).exists():
            raise serializers.ValidationError("A group with this registration number already exists.")
        return value
