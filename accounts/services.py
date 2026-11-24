from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from common.validators import normalize_email

from .models import User


class AccountService:
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
