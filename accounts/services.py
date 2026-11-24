from uuid import uuid4

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from rest_framework.request import Request
from rest_framework_simplejwt.settings import api_settings as jwt_settings

from common.validators import normalize_email

from .models import User
from .ratelimit import LoginAccountThrottle


class AccountService:
    @staticmethod
    def authenticate_user(
        *, request: HttpRequest | Request, password: str, email: str | None = None,
        username: str | None = None,
    ) -> User | None:
        email = normalize_email(email)
        lookup = {"email__iexact": email} if email else {"username": username}
        try:
            user = User.objects.get(**lookup)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            user = None
        account_email = normalize_email(user.email) if user else email
        identifier = f"email:{account_email}" if account_email else f"username:{username}"
        LoginAccountThrottle().check(identifier)
        if user is None:
            User().set_password(password)
            return None
        authenticated = authenticate(request=request, username=user.get_username(), password=password)
        if authenticated and authenticated.is_active and jwt_settings.USER_AUTHENTICATION_RULE(authenticated):
            return authenticated
        return None

    @classmethod
    def register_user(
        cls, *, first_name: str, last_name: str, email: str, phone: str, password: str,
    ) -> User:
        email = normalize_email(email)
        cls._validate_unique_contact(email, phone)
        try:
            with transaction.atomic():
                return User.objects.create_user(
                    username=uuid4().hex,
                    email=email,
                    phone=phone,
                    first_name=first_name,
                    last_name=last_name,
                    password=password,
                    is_active=True,
                    is_email_verified=False,
                    is_phone_verified=False,
                )
        except IntegrityError:
            # Check for duplicates only after the failed insert has rolled back.
            cls._validate_unique_contact(email, phone)
            raise

    @staticmethod
    def _validate_unique_contact(email: str, phone: str) -> None:
        errors = {}
        if User.objects.filter(email__iexact=email).exists():
            errors["email"] = "An account with this email address already exists."
        if User.objects.filter(phone=phone).exists():
            errors["phone_number"] = "An account with this phone number already exists."
        if errors:
            raise ValidationError(errors)
