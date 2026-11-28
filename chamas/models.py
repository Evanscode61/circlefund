from django.db import models

# Create your models here.

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
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

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SETUP
    )
    accepting_invitations = models.BooleanField(default=True)
    membership_limit = models.PositiveIntegerField(null=True, blank=True)
    allow_rejoining = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_groups",
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

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base = slugify(self.name)[:150] or "group"
            slug, n = base, 2
            while Group.objects.filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        self.email = normalize_email(self.email)
        self.phone_number = (
            normalize_phone_number(self.phone_number) or self.phone_number
        )
        super().save(*args, **kwargs)

    @transaction.atomic
    def next_member_number(self) -> str:
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

    group = models.ForeignKey(
        "chamas.Group", on_delete=models.PROTECT, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    member_number = models.CharField(max_length=30)
    role = models.ForeignKey(
        "accounts.Role",
        on_delete=models.PROTECT,
        related_name="memberships",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.INVITED
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_group_invitations",
    )
    invited_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    status_reason = models.TextField(blank=True)
    administrative_notes = models.TextField(max_length=2000, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"], name="unique_user_membership_per_group"
            ),
            models.UniqueConstraint(
                fields=["group", "member_number"], name="unique_member_number_per_group"
            ),
            models.CheckConstraint(
                condition=~Q(status="active") | Q(role__isnull=False),
                name="active_member_has_role",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "status"]),
            models.Index(fields=["user", "status"]),
        ]

    @property
    def group_role(self) -> Role | None:
        role = self.role
        return role if role is not None and role.group_id == self.group_id else None

    def __str__(self) -> str:
        return f"{self.user} - {self.group}"


class Invitation(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    group = models.ForeignKey(
        Group, on_delete=models.PROTECT, related_name="invitations"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="invitations")
    email = models.EmailField()
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="group_invitations",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_invitations",
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True)
    rejected_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                "group",
                Lower("email"),
                condition=Q(status="pending"),
                name="unique_pending_group_invite_email",
            ),
        )


class InvitationEvent(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        REVOKED = "revoked", "Revoked"

    invitation = models.ForeignKey(
        Invitation, on_delete=models.PROTECT, related_name="events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    date_created = models.DateTimeField(auto_now_add=True)
