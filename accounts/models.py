from django.contrib.auth.models import AbstractUser
from django.db import models

from base.models import BaseModel,GenericBaseModel
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

class Permission(BaseModel):
    code = models.CharField(max_length=60, unique=True)  # e.g. "loans.approve"
    description = models.CharField(max_length=200)

    def __str__(self):
        return self.code


class Role(GenericBaseModel):  # gives id, name, description, date_created, updated_at
    group = models.ForeignKey("chamas.Group", on_delete=models.PROTECT, related_name="roles")
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "name"], name="unique_role_name_per_group"),
        ]

    def __str__(self):
        return f"{self.name} ({self.group})"