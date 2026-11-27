from typing import Self

from django.core.exceptions import ValidationError
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

VERSION_CLAIM = "refresh_version"


def _session_version(user: User) -> str | None:
    version = user.refresh_token_version
    return str(version) if version is not None else None


class AccountJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token) -> User:
        user = super().get_user(validated_token)
        if validated_token.get(VERSION_CLAIM) != _session_version(user):
            raise AuthenticationFailed(
                "This session has expired. Try signing in again."
            )
        return user


class AccountRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user: User) -> Self:
        token = super().for_user(user)
        version = _session_version(user)
        if version is not None:
            token[VERSION_CLAIM] = version
        return token

    def verify(self) -> None:
        super().verify()
        try:
            version = User.objects.values_list("refresh_token_version", flat=True).get(
                **{api_settings.USER_ID_FIELD: self[api_settings.USER_ID_CLAIM]},
            )
        except (KeyError, ValidationError, User.DoesNotExist):
            raise TokenError("Refresh token is invalid.") from None
        expected = str(version) if version is not None else None
        if self.get(VERSION_CLAIM) != expected:
            raise TokenError("Refresh token is invalid.")
