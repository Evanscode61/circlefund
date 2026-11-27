from django.urls import path

from .views import (
    AcceptInvitationView,
    GroupDetailView,
    GroupListCreateView,
    GroupMembersView,
    InviteMemberView,
    MembershipUpdateView,
    RejectInvitationView,
    RevokeInvitationView,
)

urlpatterns = [
    path("groups/", GroupListCreateView.as_view(), name="group-create"),
    path(
        "groups/<uuid:group_id>/members/",
        GroupMembersView.as_view(),
        name="group-members",
    ),
    path(
        "groups/<uuid:group_id>/members/invite/",
        InviteMemberView.as_view(),
        name="group-invite-member",
    ),
    path(
        "groups/<uuid:group_id>/members/<uuid:membership_id>/",
        MembershipUpdateView.as_view(),
        name="group-membership-update",
    ),
    path(
        "groups/<uuid:group_id>/invitations/<uuid:invitation_id>/revoke/",
        RevokeInvitationView.as_view(),
        name="group-invitation-revoke",
    ),
    path(
        "invitations/<str:token>/accept/",
        AcceptInvitationView.as_view(),
        name="invitation-accept",
    ),
    path(
        "invitations/<str:token>/reject/",
        RejectInvitationView.as_view(),
        name="invitation-reject",
    ),
    path("groups/<slug:slug>/", GroupDetailView.as_view(), name="group-detail"),
]
