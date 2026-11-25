from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .serializers import AccountTokenRefreshSerializer
from .views import (
    AccountTokenView,
    ForgotPasswordView,
    LoginView,
    ProfileUpdateView,
    ProfileView,
    RegisterView,
    ResetPasswordView,
    VerifyPasswordOTPView,
)

urlpatterns = [
    #Account and Authentication
    path("register/", RegisterView.as_view(), name="user-register"),
    path("login/", LoginView.as_view(), name="user-login"),
    path("token/", AccountTokenView.as_view(), name="token_obtain_pair"),
    path(
        "token/refresh/",
        TokenRefreshView.as_view(serializer_class=AccountTokenRefreshSerializer),
        name="token_refresh",
    ),
    path("password/forgot/", ForgotPasswordView.as_view(), name="password-forgot"),
    path("password/verify-otp/", VerifyPasswordOTPView.as_view(), name="password-verify-otp"),
    path("password/reset/", ResetPasswordView.as_view(), name="password-reset"),

    #User profile
    path("me/", ProfileView.as_view(), name="account-me"),
    path("me/edit/", ProfileUpdateView.as_view(), name="account-me-update"),
]




