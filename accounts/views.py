import logging
from collections.abc import Mapping

from django.contrib.auth.models import update_last_login
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings as jwt_settings

from base.tokens import AccountRefreshToken
from common.response_provider import APIResponse

from .ratelimit import (
    LoginThrottle,
    PasswordRecoveryThrottle,
    ProfileChangeThrottle,
    RegistrationThrottle,
)
from .serializers import (
    AccountTokenSerializer,
    ChangeEmailSerializer,
    ChangePasswordSerializer,
    ChangePhoneSerializer,
    CurrentPasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    ProfileSerializer,
    RegisteredUserSerializer,
    RegistrationSerializer,
    ResetPasswordSerializer,
    VerifyPasswordOTPSerializer,
)
from .services import AccountService

logger = logging.getLogger(__name__)


class RegisterView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (RegistrationThrottle,)

    def post(self, request) -> Response:
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = AccountService.register_user(**serializer.validated_data)
        return APIResponse.created("User registered Successfully", RegisteredUserSerializer(user).data)


@method_decorator(never_cache, name="dispatch")
class LoginView(GenericAPIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (LoginThrottle,)
    serializer_class = LoginSerializer
    include_user = True

    def get_authenticate_header(self, request: Request) -> str:
        return JWTAuthentication().authenticate_header(request)

    def post(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = AccountService.authenticate_user(request=request, **serializer.validated_data)
        if user is None:
            logger.info("Account login rejected")
            raise AuthenticationFailed("Invalid email or password.")

        refresh = AccountRefreshToken.for_user(user)
        if jwt_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, user)
        logger.info("Account login succeeded for user_id=%s", user.pk)

        data: dict[str, object] = {"access": str(refresh.access_token), "refresh": str(refresh)}
        if self.include_user:
            data["user"] = LoginSerializer(user).data
        return Response(data)


class AccountTokenView(LoginView):
    serializer_class = AccountTokenSerializer
    include_user = False


@method_decorator(never_cache, name="dispatch")
class PasswordRecoveryView(GenericAPIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (PasswordRecoveryThrottle,)


class ForgotPasswordView(PasswordRecoveryView):
    serializer_class = ForgotPasswordSerializer

    def post(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AccountService.request_password_reset(**serializer.validated_data)
        return APIResponse.success(" If an account exists with this email, a verification code will be sent.. ")


class VerifyPasswordOTPView(PasswordRecoveryView):
    serializer_class = VerifyPasswordOTPSerializer

    def post(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_token = AccountService.verify_password_reset_otp(**serializer.validated_data)
        if reset_token is None:
            return APIResponse.bad_request("Invalid or expired verification code.")
        return APIResponse.success("Verification code accepted.", {"reset_token": reset_token})


class ResetPasswordView(PasswordRecoveryView):
    serializer_class = ResetPasswordSerializer

    def post(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not AccountService.reset_password(**serializer.validated_data):
            return APIResponse.bad_request("Invalid or expired reset token.")
        return APIResponse.success("Password reset successfully.")


@method_decorator(never_cache, name="dispatch")
class ProfileView(GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ProfileSerializer

    def get(self, request: Request) -> Response:
        return APIResponse.success("Your profile", self.get_serializer(request.user).data)


@method_decorator(never_cache, name="dispatch")
class ProfileUpdateView(GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ProfileSerializer
    throttle_classes = (ProfileChangeThrottle,)

    def patch(self, request: Request) -> Response:
        data = request.data
        if isinstance(data, Mapping):
            if "action" in data:
                return self._apply_action(request, data)
            if {"current_password", "new_password", "otp"}.intersection(data):
                raise ValidationError({"action": "Specify the account action."})

        serializer = self.get_serializer(request.user, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = AccountService.update_profile(request.user, **serializer.validated_data)
        return APIResponse.success("Profile updated.", self.get_serializer(profile).data)

    def _apply_action(self, request: Request, data: Mapping[str, object]) -> Response:
        actions = {
            "change_email": (ChangeEmailSerializer, self._change_email),
            "change_phone": (ChangePhoneSerializer, self._change_phone),
            "change_password": (ChangePasswordSerializer, self._change_password),
            "deactivate": (CurrentPasswordSerializer, self._deactivate),
        }
        action = data["action"]
        if not isinstance(action, str) or action not in actions:
            raise ValidationError({"action": f"Choose one of: {', '.join(actions)}."})
        serializer_class, handler = actions[action]
        serializer = serializer_class(data=data)
        unexpected = set(data).difference(serializer.fields, {"action"})
        if unexpected:
            raise ValidationError({field: "This field does not apply to this action." for field in sorted(unexpected)})
        serializer.is_valid(raise_exception=True)
        return handler(request, serializer.validated_data)

    def _change_email(self, request: Request, fields: dict[str, str]) -> Response:
        profile = AccountService.change_email(request.user, **fields)
        if "otp" not in fields:
            return APIResponse.success(
                "Check the requested email address for a verification code.",
                http_status=status.HTTP_202_ACCEPTED,
            )
        if profile is None:
            return APIResponse.bad_request("Invalid or expired verification code.")
        return APIResponse.success("Email updated. Sign in again.", self.get_serializer(profile).data)

    def _change_phone(self, request: Request, fields: dict[str, str]) -> Response:
        profile = AccountService.change_phone(request.user, **fields)
        return APIResponse.success("Phone number updated.", self.get_serializer(profile).data)

    def _change_password(self, request: Request, fields: dict[str, str]) -> Response:
        AccountService.change_password(request.user, **fields)
        return APIResponse.success("Password updated. Sign in again.")

    def _deactivate(self, request: Request, fields: dict[str, str]) -> Response:
        AccountService.deactivate(request.user, **fields)
        return APIResponse.success("Account deactivated.")
