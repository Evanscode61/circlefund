from django.db import models

# Create your models here.

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils.text import slugify

from base.models import BaseModel, GenericBaseModel
from accounts.models import Role, User
from common.validators import normalize_email, normalize_phone_number


class Group(GenericBaseModel):  # gives id, name, description, date_created, updated_at

    class GroupType(models.TextChoices):
        CHAMA = "chama", "Chama"
        SACCO = "sacco", "SACCO"
        WELFARE = "welfare", "Welfare Group"
        INVESTMENT = "investment", "Investment Group"

    class Status(models.TextChoices):
        SETUP = "setup", "Setup"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        ARCHIVED = "archived", "Archived"

    slug = models.SlugField(max_length=180, unique=True, blank=True)
    group_type = models.CharField(max_length=20, choices=GroupType.choices)
    registration_number = models.CharField(max_length=100, blank=True)

    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=16, blank=True)

    country = models.CharField(max_length=100, default="Kenya")
    currency = models.CharField(max_length=3, default="KES")
    county = models.CharField(max_length=100, blank=True)
    town = models.CharField(max_length=100, blank=True)
    physical_address = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SETUP)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_groups"
    )

    # last member number handed out; only change it through next_member_number()
    member_number_seq = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["registration_number"],
                condition=~Q(registration_number=""),
                name="unique_group_registration_number",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:150] or "group"
            slug, n = base, 2
            while Group.objects.filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        self.email = normalize_email(self.email)
        self.phone_number = normalize_phone_number(self.phone_number) or self.phone_number
        super().save(*args, **kwargs)

    @transaction.atomic
    def next_member_number(self):
        """Lock this group's row so two simultaneous joins can't get the same number."""
        locked = Group.objects.select_for_update().get(pk=self.pk)
        locked.member_number_seq += 1
        locked.save(update_fields=["member_number_seq"])
        return str(locked.member_number_seq).zfill(4)


class Membership(BaseModel):

    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        LEFT = "left", "Left Group"
        REMOVED = "removed", "Removed"

    group = models.ForeignKey("chamas.Group", on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships")
    member_number = models.CharField(max_length=30)
    role = models.ForeignKey("accounts.Role", on_delete=models.PROTECT, related_name="memberships", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INVITED)

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sent_group_invitations",
    )
    invited_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    status_reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="unique_user_membership_per_group"),
            models.UniqueConstraint(fields=["group", "member_number"], name="unique_member_number_per_group"),
            models.CheckConstraint(
                condition=~Q(status="active") | Q(role__isnull=False),
                name="active_member_has_role",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "status"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.group}"
