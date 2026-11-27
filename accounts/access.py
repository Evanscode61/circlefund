from django.db import transaction
from django.utils.text import slugify

from .models import Permission, Role

PERMISSIONS = {
    "group.manage": "Edit group settings",
    "roles.manage": "Create and edit roles",
    "members.invite": "Invite members",
    "members.manage": "Suspend, remove or change members' roles",
    "members.view": "View group members",
    "contributions.view": "View contributions",
    "contributions.record": "Record contributions",
    "contributions.manage": "Set up contribution periods and rules",
    "reconciliation.manage": "Match and resolve unmatched payments",
    "loans.apply": "Apply for a loan",
    "loans.approve": "Approve loans",
    "payments.request": "Request a payout",
    "payments.approve": "Approve a payout",
    "expenses.record": "Record expenses",
    "ledger.view": "View the group ledger",
    "reports.view": "View group reports",
}

DEFAULT_ROLES = {
    "Owner": "*",  # everything
    "Chairperson": [
        "members.invite",
        "members.manage",
        "members.view",
        "contributions.view",
        "loans.approve",
        "payments.approve",
        "ledger.view",
        "reports.view",
    ],
    "Treasurer": [
        "contributions.view",
        "contributions.record",
        "contributions.manage",
        "reconciliation.manage",
        "payments.request",
        "expenses.record",
        "ledger.view",
        "reports.view",
    ],
    "Secretary": [
        "members.invite",
        "members.view",
        "contributions.view",
        "reports.view",
    ],
    "Member": ["contributions.view", "loans.apply"],
}


@transaction.atomic
def create_default_roles(group) -> dict[str, Role]:
    """Give a new group its own copy of the default roles. Returns {name: Role}."""
    perms = {}
    for code, description in PERMISSIONS.items():
        perms[code], _ = Permission.objects.get_or_create(
            code=code, defaults={"description": description}
        )
    roles = {}
    for name, codes in DEFAULT_ROLES.items():
        role = Role.objects.create(
            group=group, name=name, code=slugify(name), is_assignable=name == "Member"
        )
        role.permissions.set(
            perms.values() if codes == "*" else [perms[c] for c in codes]
        )
        roles[name] = role
    return roles


def has_permission(membership, code) -> bool:
    """True if this membership is active and its role grants `code`."""
    if code not in PERMISSIONS:
        raise ValueError(f"Unknown permission: {code}")  # catches typos in views
    if (
        membership is None
        or membership.status != "active"
        or membership.role_id is None
        or membership.role.group_id != membership.group_id
        or not membership.role.is_active
    ):
        return False
    return membership.role.permissions.filter(code=code).exists()
