from django.contrib.auth.models import AbstractUser
from django.db import models

from base.models import BaseModel


class User(BaseModel, AbstractUser):
    phone = models.CharField(max_length=16, unique=True)
    is_phone_verified = models.BooleanField(default=False)
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_platform_admin = models.BooleanField(default=False)

    REQUIRED_FIELDS = ["email", "phone"]