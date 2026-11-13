from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.access import create_default_roles

from .models import Group, Membership


@transaction.atomic
def create_group(*, user, name, group_type, **extra):
    """Create a group in SETUP with its default roles and the creator as active Owner."""
    group = Group.objects.create(created_by=user, name=name, group_type=group_type, **extra)
    roles = create_default_roles(group)
    Membership.objects.create(
        group=group,
        user=user,
        member_number=group.next_member_number(),
        role=roles["Owner"],
        status=Membership.Status.ACTIVE,
        joined_at=timezone.now(),
    )
    return group


@transaction.atomic
def assign_role(membership, role):
    """Give a member a role, but only one that belongs to the same group."""
    if role.group_id != membership.group_id:
        raise ValidationError("This role belongs to a different group.")
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    return membership