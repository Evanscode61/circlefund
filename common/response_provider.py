from rest_framework import status
from rest_framework.response import Response


class APIResponse:
    @staticmethod
    def _build(ok, message, payload, http_status):
        body = {"status": "success" if ok else "error", "message": message}
        body["data" if ok else "errors"] = {} if payload is None else payload
        return Response(body, status=http_status)

    # ---- success ----
    @staticmethod
    def success(message, data=None, http_status=status.HTTP_200_OK):
        return APIResponse._build(True, message, data, http_status)

    @staticmethod
    def created(message, data=None):
        return APIResponse._build(True, message, data, status.HTTP_201_CREATED)

    @staticmethod
    def deleted(message="Deleted successfully"):
        return APIResponse._build(True, message, None, status.HTTP_200_OK)

    # ---- errors ----
    @staticmethod
    def bad_request(message, errors=None):
        return APIResponse._build(False, message, errors, status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def unauthorized(message="Authentication required"):
        return APIResponse._build(False, message, None, status.HTTP_401_UNAUTHORIZED)

    @staticmethod
    def forbidden(message="You do not have permission to perform this action"):
        return APIResponse._build(False, message, None, status.HTTP_403_FORBIDDEN)

    @staticmethod
    def not_found(message="Resource not found"):
        return APIResponse._build(False, message, None, status.HTTP_404_NOT_FOUND)

    @staticmethod
    def conflict(message, errors=None):
        return APIResponse._build(False, message, errors, status.HTTP_409_CONFLICT)

    @staticmethod
    def unprocessable(message, errors=None):
        return APIResponse._build(False, message, errors, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @staticmethod
    def too_many_requests(message="Too many requests received"):
        return APIRespose._build(False, message, None, status.HTTP_429_TOO_MANY_REQUESTS)

    @staticmethod
    def server_error(message="An unexpected error occurred. Please try again later"):
        return APIResponse._build(False, message, None, status.HTTP_500_INTERNAL_SERVER_ERROR)