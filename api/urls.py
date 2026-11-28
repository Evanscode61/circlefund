from django.urls import include, path

urlpatterns = [
    path("auth/", include("accounts.urls")),
    path("", include("chamas.urls")),
]
