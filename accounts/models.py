import re

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.text import slugify

from base.models import BaseModel, GenericBaseModel
from common.validators import normalize_email, normalize_phone_number


class User(BaseModel, AbstractUser):
    phone = models.CharField(max_length=16, unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=50, blank=True)
    profile_photo = models.ImageField(upload_to="profile_photos/", blank=True)
    pin_hash = models.CharField(max_length=128, blank=True, editable=False)
    is_platform_admin = models.BooleanField(default=False)
    refresh_token_version = models.UUIDField(null=True, editable=False)
    self_deactivated_at = models.DateTimeField(null=True, editable=False)

    REQUIRED_FIELDS = ["phone", "national_id"]

    def set_pin(self, raw_pin) -> None:
        """Hash a four- to six-digit PIN. Call save() to persist it."""
        if not isinstance(raw_pin, str) or re.fullmatch(r"[0-9]{4,6}", raw_pin) is None:
            raise ValidationError("Enter a PIN with four to six digits.")
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin) -> bool:
        return isinstance(raw_pin, str) and check_password(raw_pin, self.pin_hash)

    def save(self, *args, **kwargs) -> None:
        self.phone = normalize_phone_number(self.phone) or self.phone
        self.email = normalize_email(self.email) or None
        super().save(*args, **kwargs)


class OTPChallenge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=64)
    recipient = models.EmailField()
    code_hash = models.CharField(max_length=64)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("user", "purpose"), name="unique_user_otp_purpose"
            ),
        )


class Permission(BaseModel):
    code = models.CharField(max_length=60, unique=True)  # e.g. "loans.approve"
    description = models.CharField(max_length=200)

    def __str__(self) -> str:
        return self.code


class Role(GenericBaseModel):  # gives id, name, description, date_created, updated_at
    group = models.ForeignKey(
        "chamas.Group", on_delete=models.PROTECT, related_name="roles"
    )
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)
    code = models.SlugField(max_length=200, allow_unicode=True, editable=False)
    is_active = models.BooleanField(default=True)
    is_assignable = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "name"], name="unique_role_name_per_group"
            ),
            models.UniqueConstraint(
                fields=("group", "code"), name="unique_role_code_per_group"
            ),
            models.CheckConstraint(
                condition=~models.Q(code=""), name="role_code_is_not_empty"
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        if self.code:
            super().save(*args, **kwargs)
            return
        # Lock the group while allocating a code for a new custom role.
        group_model = self._meta.get_field("group").remote_field.model
        with transaction.atomic():
            group_model.objects.select_for_update(no_key=True).only("pk").get(
                pk=self.group_id
            )
            stem = slugify(self.name, allow_unicode=True)[:200] or str(self.pk)
            code, suffix = stem, 2
            while Role.objects.filter(group_id=self.group_id, code=code).exists():
                code = f"{stem[:180]}-{suffix}"
                suffix += 1
            self.code = code
            super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.group})"
