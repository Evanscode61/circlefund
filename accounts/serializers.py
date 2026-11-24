from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from common.validators import normalize_email, validate_international_phone

from .models import User


class RegistrationSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    phone_number = serializers.CharField(max_length=32, source="phone")
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128,
        style={"input_type": "password"},
    )
    password_confirmation = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128,
        style={"input_type": "password"},
    )

    def to_internal_value(self, data) -> dict[str, str]:
        if isinstance(data, dict):
            unexpected = data.keys() - self.fields.keys()
            if unexpected:
                raise serializers.ValidationError({
                    field: "This field is not accepted." for field in sorted(unexpected)
                })
        return super().to_internal_value(data)

    def validate_email(self, value) -> str:
        return normalize_email(value)

    def validate_phone_number(self, value) -> str:
        return validate_international_phone(value)

    def validate(self, attrs) -> dict[str, str]:
        password = attrs["password"]
        if password != attrs.pop("password_confirmation"):
            raise serializers.ValidationError({"password_confirmation": "Passwords must match."})
        user = User(
            first_name=attrs["first_name"], last_name=attrs["last_name"], email=attrs["email"],
        )
        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs


class RegisteredUserSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source="phone", read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "first_name", "last_name", "email", "phone_number", "is_active",
            "is_email_verified", "is_phone_verified",
        )
        read_only_fields = fields


class AccountTokenSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField(max_length=254, write_only=True, required=False)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields[self.username_field].required = False
        self.fields["password"].trim_whitespace = False

    def validate(self, attrs) -> dict[str, str]:
        email = attrs.get("email")
        if email:
            try:
                user = User.objects.get(email__iexact=normalize_email(email))
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                # Match the password hashing work Django performs for unknown usernames.
                User().set_password(attrs["password"])
                raise AuthenticationFailed(
                    self.error_messages["no_active_account"], "no_active_account",
                ) from None
            attrs[self.username_field] = user.get_username()
        elif self.username_field not in attrs:
            raise serializers.ValidationError({"email": "Enter your email address."})
        return super().validate(attrs)
