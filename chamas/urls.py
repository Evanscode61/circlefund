from django.urls import path

from .views import (
    GroupDetailView,
    GroupListCreateView,
    GroupMembersView,
    MembershipUpdateView,
)

urlpatterns = [
    path("groups/", GroupListCreateView.as_view(), name="group-create"),
    path("groups/<uuid:group_id>/members/", GroupMembersView.as_view(), name="group-members"),
    path(
        "groups/<uuid:group_id>/members/<uuid:membership_id>/",
        MembershipUpdateView.as_view(),
        name="group-membership-update",
    ),
    path("groups/<slug:slug>/", GroupDetailView.as_view(), name="group-detail"),
]
