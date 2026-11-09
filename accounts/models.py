from django.contrib.auth.models import AbstractUser
from django.db import models

from base.models import BaseModel
from common.validators import normalize_email, normalize_phone_number

""" User model"""
class User(BaseModel, AbstractUser):
    phone = models.CharField(max_length=16, unique=True)
    email = models.EmailField(unique=True)
    is_phone_verified = models.BooleanField(default=False)
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_platform_admin = models.BooleanField(default=False)

    REQUIRED_FIELDS = ["email", "phone"]

     # save the phone numbers and emails in one standard formats to avoid mismatch on the database

    def save(self, *args, **kwargs):
        self.phone = normalize_phone_number(self.phone) or self.phone
        self.email = normalize_email(self.email) or None
        super().save(*args, **kwargs)