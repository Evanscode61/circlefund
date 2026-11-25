from typing import Self

from django.core.exceptions import ValidationError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User


class AccountRefreshToken(RefreshToken):
    version_claim = "refresh_version"
    no_copy_claims = (*RefreshToken.no_copy_claims, version_claim)

    @classmethod
    def for_user(cls, user: User) -> Self:
        token = super().for_user(user)
        if user.refresh_token_version is not None:
            token[cls.version_claim] = str(user.refresh_token_version)
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
        if self.get(self.version_claim) != expected:
            raise TokenError("Refresh token is invalid.")
