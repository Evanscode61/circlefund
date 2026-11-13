import logging

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

from .responses import APIResponse

lgr = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        exc = ValidationError(detail)

    response = exception_handler(exc, context)

    if response is None:  # not a DRF error: a real bug
        if settings.DEBUG:
            return None  # let Django show its debug page while developing
        lgr.exception("Unhandled error in %s", context["view"].__class__.__name__)
        return APIResponse.server_error()

    code, data = response.status_code, response.data
    detail = data.get("detail") if isinstance(data, dict) else None

    if code == 400:
        return APIResponse.bad_request("Validation failed", data)
    if code == 401:
        new = APIResponse.unauthorized(str(detail) if detail else "Authentication required")
        header = response.get("WWW-Authenticate")
        if header:
            new["WWW-Authenticate"] = header
        return new
    if code == 403:
        return APIResponse.forbidden(str(detail) if detail else "Permission denied")
    if code == 404:
        return APIResponse.not_found(str(detail) if detail else "Resource not found")
    return response