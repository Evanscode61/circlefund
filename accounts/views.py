import logging

from django.contrib.auth.models import update_last_login
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from common.response_provider import APIResponse

from .ratelimit import LoginThrottle, RegistrationThrottle
from .serializers import (
    AccountTokenSerializer,
    LoginSerializer,
    RegisteredUserSerializer,
    RegistrationSerializer,
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

        refresh = RefreshToken.for_user(user)
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
