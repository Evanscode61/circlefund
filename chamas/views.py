from django.shortcuts import render

# Create your views here.
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response_provider import APIResponse

from .serializers import GroupSerializer
from .services import create_group


class  GroupCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = GroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # errors go through the exception handler
        group = create_group(user=request.user, **serializer.validated_data)
        membership = group.memberships.select_related("role").get(user=request.user)
        return APIResponse.created(
            "Group created",
            {
                "group": GroupSerializer(group).data,
                "membership": {
                    "member_number": membership.member_number,
                    "role": membership.role.name,
                    "status": membership.status,
                },
            },
        )
