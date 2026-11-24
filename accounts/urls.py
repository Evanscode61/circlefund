from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import AccountTokenView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="user-register"),
    path("token/", AccountTokenView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]
