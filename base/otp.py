import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from accounts.models import OTPChallenge, User


class OTPService:
    lifetime = timedelta(minutes=5)
    resend_cooldown = timedelta(seconds=60)
    max_attempts = 5

    @staticmethod
    def _generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _digest(user: User, purpose: str, recipient: str, code: str) -> str:
        return salted_hmac(
            "accounts.otp",
            f"{user.pk}:{purpose}:{recipient}:{code}",
            algorithm="sha256",
        ).hexdigest()

    @classmethod
    @transaction.atomic
    def issue(cls, *, user: User, purpose: str, recipient: str) -> str | None:
        # Lock the user even when there is no challenge row to lock yet.
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        challenge = (
            OTPChallenge.objects.select_for_update()
            .filter(user=user, purpose=purpose)
            .first()
        )
        now = timezone.now()
        if challenge is not None and now < challenge.issued_at + cls.resend_cooldown:
            return None

        code = cls._generate_code()
        while challenge is not None and constant_time_compare(
            challenge.code_hash, cls._digest(user, purpose, challenge.recipient, code)
        ):
            code = cls._generate_code()

        if challenge is None:
            challenge = OTPChallenge(user=user, purpose=purpose)
        challenge.recipient = recipient
        challenge.code_hash = cls._digest(user, purpose, recipient, code)
        challenge.issued_at = now
        challenge.expires_at = now + cls.lifetime
        challenge.attempts = 0
        challenge.consumed_at = None
        challenge.save()
        return code

    @classmethod
    @transaction.atomic
    def verify(cls, *, user: User, purpose: str, recipient: str, code: str) -> bool:
        challenge = (
            OTPChallenge.objects.select_for_update()
            .filter(user=user, purpose=purpose)
            .first()
        )
        now = timezone.now()
        if (
            challenge is None
            or challenge.recipient != recipient
            or challenge.consumed_at is not None
            or challenge.expires_at <= now
            or challenge.attempts >= cls.max_attempts
        ):
            return False
        if not constant_time_compare(
            challenge.code_hash, cls._digest(user, purpose, recipient, code)
        ):
            challenge.attempts += 1
            challenge.save(update_fields=("attempts",))
            return False
        challenge.consumed_at = now
        challenge.save(update_fields=("consumed_at",))
        return True

    @staticmethod
    def invalidate(*, user: User, purpose: str) -> None:
        OTPChallenge.objects.filter(
            user=user, purpose=purpose, consumed_at__isnull=True
        ).update(
            consumed_at=timezone.now(),
        )
