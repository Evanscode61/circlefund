from collections.abc import Callable, Mapping, Sequence
from typing import TypeVar

from django.core.paginator import EmptyPage, Paginator
from django.db.models import QuerySet
from django.http import HttpRequest
from rest_framework.request import Request
from rest_framework.response import Response

from common.response_provider import APIResponse

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
Item = TypeVar("Item")


def paginated_response(
    request: HttpRequest | Request,
    queryset: QuerySet[Item] | Sequence[Item],
    collection_name: str,
    payload_fn: Callable[[Item], Mapping[str, object]],
    *,
    message: str = "Results retrieved.",
) -> Response:
    """Serialize one page of an ordered collection into Circlefund's response format."""
    try:
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        page = page_size = 0

    if page < 1 or page_size < 1:
        return APIResponse.bad_request(
            "page and page_size must be positive integers.",
            errors={"code": "invalid_pagination"},
        )

    paginator = Paginator(queryset, min(page_size, MAX_PAGE_SIZE))
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        return APIResponse.bad_request(
            "page is out of range.",
            errors={"code": "invalid_pagination"},
        )

    return APIResponse.success(message, data={
        collection_name: [payload_fn(item) for item in page_obj.object_list],
        "pagination": {
            "page": page_obj.number,
            "page_size": paginator.per_page,
            "total_items": paginator.count,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
    })
