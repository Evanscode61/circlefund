from collections.abc import Callable
from functools import wraps
from uuid import UUID

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.access import has_permission
from chamas.models import Membership
from common.response_provider import APIResponse


def require_permission(
    code: str,
    *,
    message: str = "You do not have permission to perform this action.",
) -> Callable[[Callable[..., Response]], Callable[..., Response]]:
    """Require an active membership and a role permission for a view with a group_id URL parameter."""
    def decorate(handler: Callable[..., Response]) -> Callable[..., Response]:
        @wraps(handler)
        def wrapped(view, request: Request, group_id: UUID, **kwargs) -> Response:
            if not request.user.is_authenticated:
                raise NotAuthenticated
            membership = get_object_or_404(
                Membership.objects.select_related("role"),
                group_id=group_id, user=request.user, status=Membership.Status.ACTIVE,
            )
            if not has_permission(membership, code):
                return APIResponse.forbidden(message)
            return handler(view, request, group_id=group_id, **kwargs)
        return wrapped
    return decorate
