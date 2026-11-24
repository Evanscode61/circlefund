from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from common.response_provider import APIResponse

from .ratelimit import RegistrationThrottle
from .serializers import (
    AccountTokenSerializer,
    RegisteredUserSerializer,
    RegistrationSerializer,
)
from .services import AccountService


class RegisterView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (RegistrationThrottle,)

    def post(self, request) -> Response:
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = AccountService.register_user(**serializer.validated_data)
        return APIResponse.created("User registered Successfully", RegisteredUserSerializer(user).data)


class AccountTokenView(TokenObtainPairView):
    serializer_class = AccountTokenSerializer
