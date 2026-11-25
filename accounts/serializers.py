from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from base.tokens import AccountRefreshToken
from common.validators import (
    normalize_email,
    validate_international_phone,
    validate_not_in_future,
)

from .models import User

OTP_PATTERN = r"\A[0-9]{6}\Z"


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
            "is_email_verified", "is_phone_verified", "date_created",
        )
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(max_length=254)
    email_verified = serializers.BooleanField(source="is_email_verified", read_only=True)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=4096,
        style={"input_type": "password"},
    )

    def validate_email(self, value: str) -> str:
        return normalize_email(value)


class AccountTokenSerializer(LoginSerializer):
    email = serializers.EmailField(max_length=254, write_only=True, required=False)
    username = serializers.CharField(max_length=150, write_only=True, required=False)

    def validate(self, attrs) -> dict[str, str]:
        if "email" not in attrs and "username" not in attrs:
            raise serializers.ValidationError({"email": "Enter your email address."})
        return attrs


class AccountTokenRefreshSerializer(TokenRefreshSerializer):
    token_class = AccountRefreshToken


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class VerifyPasswordOTPSerializer(ForgotPasswordSerializer):
    otp = serializers.RegexField(OTP_PATTERN, max_length=6, write_only=True)


class ResetPasswordSerializer(serializers.Serializer):
    reset_token = serializers.CharField(max_length=512, write_only=True)
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128,
        style={"input_type": "password"},
    )


class ProfileSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(source="phone", read_only=True)
    date_of_birth = serializers.DateField(
        required=False, allow_null=True, validators=[validate_not_in_future],
    )
    profile_photo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = (
            "id", "first_name", "last_name", "date_of_birth", "gender", "profile_photo",
            "email", "phone_number", "is_email_verified", "is_phone_verified", "date_created",
        )
        read_only_fields = (
            "id", "email", "is_email_verified", "is_phone_verified", "date_created",
        )


class CurrentPasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=4096,
        style={"input_type": "password"},
    )


class ChangeEmailSerializer(CurrentPasswordSerializer):
    email = serializers.EmailField(max_length=254)
    otp = serializers.RegexField(OTP_PATTERN, max_length=6, write_only=True, required=False)

    def validate_email(self, value: str) -> str:
        return normalize_email(value)


class ChangePhoneSerializer(CurrentPasswordSerializer):
    phone_number = serializers.CharField(max_length=32)

    def validate_phone_number(self, value: str) -> str:
        return validate_international_phone(value)


class ChangePasswordSerializer(CurrentPasswordSerializer):
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128,
        style={"input_type": "password"},
    )
