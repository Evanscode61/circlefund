from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.response_provider import APIResponse

from .models import Membership
from .serializers import GroupSerializer, MembershipSerializer
from .services import create_group


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
