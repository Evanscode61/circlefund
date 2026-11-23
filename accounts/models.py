import re

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from base.models import BaseModel
from common.validators import normalize_email, normalize_phone_number


class User(BaseModel, AbstractUser):
    phone = models.CharField(max_length=16, unique=True)
    email = models.EmailField(unique=True)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=50, blank=True)
    profile_photo = models.ImageField(upload_to="profile_photos/", blank=True)
    pin_hash = models.CharField(max_length=128, blank=True, editable=False)
    is_platform_admin = models.BooleanField(default=False)

    REQUIRED_FIELDS = ["email", "phone"]

    def set_pin(self, raw_pin):
        """Hash a four- to six-digit PIN. Call save() to persist it."""
        if not isinstance(raw_pin, str) or re.fullmatch(r"[0-9]{4,6}", raw_pin) is None:
            raise ValidationError("Enter a PIN with four to six digits.")
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin):
        return isinstance(raw_pin, str) and check_password(raw_pin, self.pin_hash)

    def save(self, *args, **kwargs):
        self.phone = normalize_phone_number(self.phone) or self.phone
        self.email = normalize_email(self.email) or None
        super().save(*args, **kwargs)
