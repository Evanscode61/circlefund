import logging
from functools import partial
from smtplib import SMTPException
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from kombu.exceptions import OperationalError
from rest_framework.request import Request
from rest_framework_simplejwt.settings import api_settings as jwt_settings

from base.otp import OTPService
from base.tasks import deliver_password_reset_otp
from common.validators import normalize_email

from .models import User
from .ratelimit import LoginAccountThrottle

logger = logging.getLogger(__name__)
password_reset_tokens = PasswordResetTokenGenerator()
password_reset_tokens.key_salt = "accounts.password-reset.authorization"


class AccountService:
    password_reset_purpose = "password_reset"

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

    @classmethod
    def request_password_reset(cls, *, email: str) -> None:
        email = normalize_email(email)
        if not settings.CELERY_BROKER_URL:
            cls.deliver_password_reset_otp(email=email)
            return
        try:
            # Queue the request before looking up the account. The task generates the OTP.
            deliver_password_reset_otp.apply_async(kwargs={"email": email}, retry=False)
        except (OSError, OperationalError):
            logger.warning("Could not queue password recovery email.")

    @classmethod
    @transaction.atomic
    def deliver_password_reset_otp(cls, *, email: str) -> None:
        user = cls._find_recovery_user(email)
        if user is None:
            return
        code = OTPService.issue(
            user=user, purpose=cls.password_reset_purpose, recipient=normalize_email(user.email),
        )
        if code is not None:
            transaction.on_commit(partial(cls._send_password_reset_email, user.email, code))

    @classmethod
    @transaction.atomic
    def verify_password_reset_otp(cls, *, email: str, otp: str) -> str | None:
        user = cls._find_recovery_user(email)
        if user is None or not OTPService.verify(
            user=user, purpose=cls.password_reset_purpose, recipient=normalize_email(user.email), code=otp,
        ):
            return None
        return f"{user.pk}.{password_reset_tokens.make_token(user)}"

    @classmethod
    @transaction.atomic
    def reset_password(cls, *, reset_token: str, new_password: str) -> bool:
        try:
            encoded_user_id, proof = reset_token.split(".", 1)
            user_id = UUID(encoded_user_id)
        except ValueError:
            return False

        user = User.objects.select_for_update().filter(pk=user_id, is_active=True).first()
        if user is None or not password_reset_tokens.check_token(user, proof):
            return False

        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            raise ValidationError({"new_password": exc.messages}) from exc

        user.set_password(new_password)
        user.refresh_token_version = uuid4()
        user.save(update_fields=("password", "refresh_token_version", "updated_at"))
        OTPService.invalidate(user=user, purpose=cls.password_reset_purpose)
        return True

    @staticmethod
    def _find_recovery_user(email: str) -> User | None:
        try:
            user = User.objects.select_for_update().get(email__iexact=normalize_email(email))
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            return None
        return user if user.is_active else None

    @staticmethod
    def _send_password_reset_email(recipient: str, code: str) -> None:
        try:
            send_mail(
                "Circlefund password reset code",
                f"Your Circlefund password reset code is {code}. It expires in 5 minutes. "
                "If you did not request a password reset, you can ignore this email.",
                None,
                [recipient],
            )
        except (OSError, SMTPException):
            logger.warning("Could not deliver password recovery email.")
