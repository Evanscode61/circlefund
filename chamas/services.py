from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.access import create_default_roles
from accounts.models import Role

from .models import Group, Membership


@transaction.atomic
def create_group(*, user, name, group_type, **extra) -> Group:
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
def assign_role(membership, role) -> Membership:
    """Give a member a role, but only one that belongs to the same group."""
    if role.group_id != membership.group_id:
        raise ValidationError("This role belongs to a different group.")
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    return membership


def list_memberships(
    group_id: UUID, *, search: str = "", status: str | None = None, role: str | None = None,
) -> QuerySet[Membership]:
    memberships = Membership.objects.filter(group_id=group_id).select_related("user", "role")
    if status is not None:
        memberships = memberships.filter(status=status)
    if role is not None:
        role_filter = role.casefold()
        group_roles = Role.objects.filter(group_id=group_id).only("name")
        role_ids = [
            group_role.pk for group_role in group_roles
            if role_filter in (group_role.code.casefold(), str(group_role.pk))
        ]
        memberships = memberships.filter(role_id__in=role_ids)
    for term in search.split():
        memberships = memberships.filter(
            Q(user__first_name__icontains=term)
            | Q(user__last_name__icontains=term)
            | Q(user__email__icontains=term)
            | Q(member_number__icontains=term),
        )
    return memberships.order_by("member_number", "pk")
