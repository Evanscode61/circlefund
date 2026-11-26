from uuid import UUID

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import has_permission
from common.response_provider import APIResponse
from utils.pagination import paginated_response

from .models import Membership
from .serializers import (
    GroupMemberSerializer,
    GroupMembersQuerySerializer,
    GroupSerializer,
    MembershipSerializer,
)
from .services import create_group, list_memberships


def membership_payload(membership) -> dict[str, object]:
    return {
        "group": GroupSerializer(membership.group).data,
        "membership": MembershipSerializer(membership).data,
    }


class GroupListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        memberships = (
            Membership.objects.filter(user=request.user, status=Membership.Status.ACTIVE)
            .select_related("group", "role")
            .order_by("group__name")
        )
        return APIResponse.success("Your groups", [membership_payload(m) for m in memberships])

    def post(self, request) -> Response:
        serializer = GroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = create_group(user=request.user, **serializer.validated_data)
        membership = group.memberships.select_related("group", "role").get(user=request.user)
        return APIResponse.created("Group created", membership_payload(membership))


class GroupDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug) -> Response:
        # non-members get a 404, so the API never confirms a group exists
        membership = get_object_or_404(
            Membership.objects.select_related("group", "role"),
            group__slug=slug, user=request.user, status=Membership.Status.ACTIVE,
        )
        data = membership_payload(membership)
        data["permissions"] = sorted(membership.role.permissions.values_list("code", flat=True))
        return APIResponse.success("Group details", data)


class GroupMembersView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, group_id: UUID) -> Response:
        membership = get_object_or_404(
            Membership.objects.select_related("role"),
            group_id=group_id, user=request.user, status=Membership.Status.ACTIVE,
        )
        if not has_permission(membership, "members.view"):
            return APIResponse.forbidden("You do not have permission to view group members.")

        query = GroupMembersQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        memberships = list_memberships(group_id, **query.validated_data)
        serializer = GroupMemberSerializer()
        return paginated_response(
            request, memberships, "results", serializer.to_representation,
            message="Members retrieved successfully", include_count=True,
        )
