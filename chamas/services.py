import logging
from datetime import timedelta
from functools import partial
from hashlib import sha256
from secrets import token_urlsafe
from smtplib import SMTPException
from uuid import UUID

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound

from accounts.access import DEFAULT_ROLES, create_default_roles, has_permission
from accounts.models import Role, User
from common.exceptions import InvitationConflict
from common.validators import normalize_email

from .models import Group, Invitation, InvitationEvent, Membership

logger = logging.getLogger(__name__)


class GroupService:
    @staticmethod
    @transaction.atomic
    def create_group(*, user: User, name: str, group_type: str, **extra) -> Group:
        """Create a group in SETUP with its default roles and the creator as active Owner."""
        group = Group.objects.create(
            created_by=user, name=name, group_type=group_type, **extra
        )
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


class MembershipService:
    @staticmethod
    @transaction.atomic
    def assign_role(membership: Membership, role: Role) -> Membership:
        """Give a member a role, but only one that belongs to the same group."""
        if role.group_id != membership.group_id:
            raise ValidationError("This role belongs to a different group.")
        membership.role = role
        membership.save(update_fields=["role", "updated_at"])
        return membership

    @staticmethod
    def list_memberships(
        group_id: UUID,
        *,
        search: str = "",
        status: str | None = None,
        role: str | None = None,
    ) -> QuerySet[Membership]:
        memberships = Membership.objects.filter(group_id=group_id).select_related(
            "user", "role"
        )
        if status is not None:
            memberships = memberships.filter(status=status)
        if role is not None:
            role_filter = Q(role__code__iexact=role)
            try:
                role_filter |= Q(role_id=UUID(role))
            except ValueError:
                pass
            memberships = memberships.filter(role_filter, role__group_id=group_id)
        for term in search.split():
            memberships = memberships.filter(
                Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__email__icontains=term)
                | Q(member_number__icontains=term),
            )
        return memberships.order_by("member_number", "pk")

    @staticmethod
    @transaction.atomic
    def update_membership_notes(
        *,
        group_id: UUID,
        membership_id: UUID,
        administrative_notes: str,
    ) -> Membership:
        membership = Membership.objects.select_for_update().get(
            pk=membership_id, group_id=group_id
        )
        if membership.administrative_notes != administrative_notes:
            membership.administrative_notes = administrative_notes
            membership.save(update_fields=("administrative_notes", "updated_at"))
        return membership


class InvitationService:
    @classmethod
    @transaction.atomic
    def invite(
        cls, *, group_id: UUID, actor: User, email: str, role_code: str
    ) -> Invitation:
        group = cls._lock_group(group_id)
        membership = cls._require_permission(group, actor, "members.invite")
        cls._check_group_open(group)
        role = cls._assignable_role(group, code=role_code)
        if role is None:
            raise ValidationError(
                {"role_code": "Choose an active, assignable role in this group."}
            )
        cls._check_role_delegation(membership, role)
        email = normalize_email(email)
        if group.memberships.filter(
            status=Membership.Status.ACTIVE, user__email__iexact=email
        ).exists():
            raise InvitationConflict("This email already belongs to an active member.")

        now = timezone.now()
        pending = group.invitations.filter(
            email__iexact=email, status=Invitation.Status.PENDING
        )
        pending.filter(expires_at__lte=now).update(
            status=Invitation.Status.EXPIRED, updated_at=now
        )
        if pending.exists():
            raise InvitationConflict("An invitation is already pending for this email.")
        cls._check_capacity(group)

        try:
            invited_user = User.objects.get(email__iexact=email)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            invited_user = None

        token = token_urlsafe(32)
        invitation = Invitation.objects.create(
            group=group,
            email=email,
            role=role,
            invited_by=actor,
            invited_user=invited_user,
            token_hash=cls._token_hash(token),
            expires_at=now + timedelta(hours=settings.GROUP_INVITATION_TTL_HOURS),
        )
        InvitationEvent.objects.create(
            invitation=invitation, actor=actor, action=InvitationEvent.Action.CREATED
        )
        transaction.on_commit(partial(cls._send_email, invitation, token))
        return invitation

    @classmethod
    @transaction.atomic
    def accept(cls, *, token: str, actor: User) -> Membership:
        invitation, actor = cls._lock_recipient_invitation(token, actor)
        group = invitation.group
        cls._check_group_open(group)
        role = cls._assignable_role(group, pk=invitation.role_id)
        if role is None:
            raise InvitationConflict("The invited role is no longer available.")
        membership = group.memberships.select_for_update().filter(user=actor).first()
        if membership is not None:
            if membership.status == Membership.Status.ACTIVE:
                raise InvitationConflict("You are already an active member.")
            if membership.status == Membership.Status.SUSPENDED:
                raise InvitationConflict(
                    "A suspended membership cannot be restored through an invitation."
                )
            if (
                membership.status in (Membership.Status.LEFT, Membership.Status.REMOVED)
                and not group.allow_rejoining
            ):
                raise InvitationConflict(
                    "This group does not allow former members to rejoin."
                )
        cls._check_capacity(group)

        now = timezone.now()
        if membership is None:
            membership = Membership(
                group=group, user=actor, member_number=group.next_member_number()
            )
        membership.role = role
        membership.status = Membership.Status.ACTIVE
        membership.invited_by_id = invitation.invited_by_id
        membership.invited_at = invitation.date_created
        membership.joined_at = now
        membership.left_at = None
        membership.status_reason = ""
        membership.save()

        invitation.invited_user = actor
        invitation.status = Invitation.Status.ACCEPTED
        invitation.accepted_at = now
        invitation.save(
            update_fields=("invited_user", "status", "accepted_at", "updated_at")
        )
        InvitationEvent.objects.create(
            invitation=invitation, actor=actor, action=InvitationEvent.Action.ACCEPTED
        )
        return membership

    @classmethod
    @transaction.atomic
    def reject(cls, *, token: str, actor: User) -> Invitation:
        invitation, actor = cls._lock_recipient_invitation(token, actor)
        invitation.invited_user = actor
        invitation.status = Invitation.Status.REJECTED
        invitation.rejected_at = timezone.now()
        invitation.save(
            update_fields=("invited_user", "status", "rejected_at", "updated_at")
        )
        InvitationEvent.objects.create(
            invitation=invitation, actor=actor, action=InvitationEvent.Action.REJECTED
        )
        return invitation

    @classmethod
    @transaction.atomic
    def revoke(cls, *, group_id: UUID, invitation_id: UUID, actor: User) -> Invitation:
        group = cls._lock_group(group_id)
        cls._require_permission(group, actor, "members.manage")
        invitation = (
            group.invitations.select_for_update().filter(pk=invitation_id).first()
        )
        if invitation is None:
            raise NotFound("Invitation not found.")
        cls._check_pending(invitation)
        invitation.status = Invitation.Status.REVOKED
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=("status", "revoked_at", "updated_at"))
        InvitationEvent.objects.create(
            invitation=invitation, actor=actor, action=InvitationEvent.Action.REVOKED
        )
        return invitation

    @classmethod
    def _lock_recipient_invitation(
        cls, token: str, actor: User
    ) -> tuple[Invitation, User]:
        token_hash = cls._token_hash(token)
        group_id = (
            Invitation.objects.filter(token_hash=token_hash)
            .values_list("group_id", flat=True)
            .first()
        )
        if group_id is None:
            raise NotFound("Invitation not found.")
        actor = User.objects.select_for_update(no_key=True).get(pk=actor.pk)
        group = cls._lock_group(group_id)
        invitation = (
            group.invitations.select_for_update().filter(token_hash=token_hash).first()
        )
        if (
            invitation is None
            or not actor.is_active
            or normalize_email(actor.email) != invitation.email
            or invitation.invited_user_id not in (None, actor.pk)
        ):
            raise NotFound("Invitation not found.")
        if not actor.is_email_verified:
            raise PermissionDenied(
                "Verify your email address before responding to this invitation."
            )
        cls._check_pending(invitation)
        invitation.group = group
        return invitation, actor

    @staticmethod
    def _lock_group(group_id: UUID) -> Group:
        group = Group.objects.select_for_update(no_key=True).filter(pk=group_id).first()
        if group is None:
            raise NotFound("Group not found.")
        return group

    @staticmethod
    def _require_permission(group: Group, actor: User, permission: str) -> Membership:
        membership = (
            group.memberships.select_related("role")
            .filter(
                user=actor,
                status=Membership.Status.ACTIVE,
            )
            .first()
        )
        if membership is None:
            raise NotFound("Group not found.")
        if not has_permission(membership, permission):
            raise PermissionDenied("You do not have permission to perform this action.")
        return membership

    @staticmethod
    def _check_pending(invitation: Invitation) -> None:
        if (
            invitation.status != Invitation.Status.PENDING
            or invitation.expires_at <= timezone.now()
        ):
            raise InvitationConflict("This invitation is no longer available.")

    @staticmethod
    def _check_group_open(group: Group) -> None:
        if group.status != Group.Status.ACTIVE or not group.accepting_invitations:
            raise InvitationConflict("This group is not accepting invitations.")

    @staticmethod
    def _check_capacity(group: Group) -> None:
        if (
            group.membership_limit is not None
            and group.memberships.filter(
                status__in=(Membership.Status.ACTIVE, Membership.Status.SUSPENDED),
            ).count()
            >= group.membership_limit
        ):
            raise InvitationConflict("The group has reached its membership limit.")

    @staticmethod
    def _assignable_role(group: Group, **lookup) -> Role | None:
        return (
            group.roles.select_for_update(no_key=True)
            .filter(
                is_active=True,
                is_assignable=True,
                **lookup,
            )
            .exclude(code="owner")
            .first()
        )

    @staticmethod
    def _check_role_delegation(membership: Membership, role: Role) -> None:
        permissions = set(membership.role.permissions.values_list("code", flat=True))
        if role.code == "member":
            permissions.update(DEFAULT_ROLES["Member"])
        if role.permissions.exclude(code__in=permissions).exists():
            raise PermissionDenied(
                "You cannot invite someone to a role with permissions you cannot grant."
            )

    @staticmethod
    def _token_hash(token: str) -> str:
        return sha256(token.encode()).hexdigest()

    @staticmethod
    def _send_email(invitation: Invitation, token: str) -> None:
        url = f"{settings.GROUP_INVITATION_FRONTEND_URL.rstrip('/')}/{token}"
        try:
            send_mail(
                "Circlefund group invitation",
                f"You have been invited to join a Circlefund group. Open this link to respond:\n\n{url}",
                None,
                [invitation.email],
            )
        except (OSError, SMTPException):
            logger.warning("Could not send group invitation %s.", invitation.pk)
