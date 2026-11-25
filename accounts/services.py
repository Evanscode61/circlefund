import logging
from functools import partial
from smtplib import SMTPException
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
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
    email_change_purpose = "email_change"

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
    def _validate_unique_contact(
        email: str | None = None, phone: str | None = None, *, exclude_user: User | None = None,
    ) -> None:
        users = User.objects.all()
        if exclude_user is not None:
            users = users.exclude(pk=exclude_user.pk)
        errors = {}
        if email is not None and users.filter(email__iexact=email).exists():
            errors["email"] = "An account with this email address already exists."
        if phone is not None and users.filter(phone=phone).exists():
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
            logger.warning("Could not queue account verification email.")

    @classmethod
    @transaction.atomic
    def deliver_password_reset_otp(cls, *, email: str) -> None:
        user = cls._lock_user_by_email(email)
        if user is not None and user.is_active:
            cls._issue_email_code(user, cls.password_reset_purpose, user.email, "password reset")

    @classmethod
    @transaction.atomic
    def verify_password_reset_otp(cls, *, email: str, otp: str) -> str | None:
        user = cls._lock_user_by_email(email)
        if user is None or not user.is_active or not OTPService.verify(
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
        cls._set_password(user, new_password)
        return True

    @classmethod
    def _set_password(cls, user: User, new_password: str) -> None:
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            raise ValidationError({"new_password": exc.messages}) from exc

        user.set_password(new_password)
        user.refresh_token_version = uuid4()
        user.save(update_fields=("password", "refresh_token_version", "updated_at"))
        OTPService.invalidate(user=user, purpose=cls.password_reset_purpose)
        OTPService.invalidate(user=user, purpose=cls.email_change_purpose)

    @staticmethod
    @transaction.atomic
    def update_profile(user: User, **changes) -> User:
        user = AccountService._lock_active_account(user)
        if changes:
            for field, value in changes.items():
                setattr(user, field, value)
            user.save(update_fields=(*changes, "updated_at"))
        return user

    @classmethod
    @transaction.atomic
    def change_email(
        cls, user: User, *, email: str, current_password: str, otp: str | None = None,
    ) -> User | None:
        user = cls._confirm_current_password(user, current_password)
        email = normalize_email(email)
        if email == user.email and user.is_email_verified:
            raise ValidationError({"email": "This email address is already verified on your account."})
        cls._validate_unique_contact(email=email, exclude_user=user)
        if otp is None:
            cls._issue_email_code(user, cls.email_change_purpose, email, "email change")
            return None
        if not OTPService.verify(user=user, purpose=cls.email_change_purpose, recipient=email, code=otp):
            return None

        try:
            with transaction.atomic():
                user.email = email
                user.is_email_verified = True
                user.refresh_token_version = uuid4()
                user.save(update_fields=("email", "is_email_verified", "refresh_token_version", "updated_at"))
        except IntegrityError:
            cls._validate_unique_contact(email=email, exclude_user=user)
            raise
        OTPService.invalidate(user=user, purpose=cls.password_reset_purpose)
        return user

    @classmethod
    @transaction.atomic
    def change_phone(cls, user: User, *, phone_number: str, current_password: str) -> User:
        user = cls._confirm_current_password(user, current_password)
        if phone_number == user.phone:
            return user
        cls._validate_unique_contact(phone=phone_number, exclude_user=user)
        try:
            with transaction.atomic():
                user.phone = phone_number
                user.is_phone_verified = False
                user.save(update_fields=("phone", "is_phone_verified", "updated_at"))
        except IntegrityError:
            cls._validate_unique_contact(phone=phone_number, exclude_user=user)
            raise
        return user

    @classmethod
    @transaction.atomic
    def change_password(cls, user: User, *, current_password: str, new_password: str) -> None:
        user = cls._confirm_current_password(user, current_password)
        cls._set_password(user, new_password)

    @classmethod
    @transaction.atomic
    def deactivate(cls, user: User, *, current_password: str) -> None:
        user = cls._confirm_current_password(user, current_password)
        user.is_active = False
        user.self_deactivated_at = timezone.now()
        user.refresh_token_version = uuid4()
        user.save(update_fields=("is_active", "self_deactivated_at", "refresh_token_version", "updated_at"))
        for purpose in (cls.password_reset_purpose, cls.email_change_purpose):
            OTPService.invalidate(user=user, purpose=purpose)

    @staticmethod
    def _lock_active_account(user: User) -> User:
        current = User.objects.select_for_update().filter(pk=user.pk, is_active=True).first()
        if current is None or current.refresh_token_version != user.refresh_token_version:
            raise PermissionDenied("This account session is no longer active.")
        return current

    @classmethod
    def _confirm_current_password(cls, user: User, password: str) -> User:
        user = cls._lock_active_account(user)
        if not user.check_password(password):
            raise ValidationError({"current_password": "Incorrect password."})
        return user

    @staticmethod
    def _lock_user_by_email(email: str) -> User | None:
        try:
            return User.objects.select_for_update().get(email__iexact=normalize_email(email))
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            return None

    @classmethod
    def _issue_email_code(cls, user: User, purpose: str, recipient: str, action: str) -> None:
        code = OTPService.issue(user=user, purpose=purpose, recipient=normalize_email(recipient))
        if code is not None:
            transaction.on_commit(partial(cls._send_email_code, recipient, code, action))

    @staticmethod
    def _send_email_code(recipient: str, code: str, action: str) -> None:
        try:
            send_mail(
                f"Circlefund {action} code",
                f"Your Circlefund {action} code is {code}. It expires in 5 minutes. "
                "If you did not request this code, you can ignore this email.",
                None,
                [recipient],
            )
        except (OSError, SMTPException):
            logger.warning("Could not deliver account verification email.")
