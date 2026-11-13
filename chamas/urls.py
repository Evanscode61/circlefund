from django.urls import path

from .views import GroupCreateView

urlpatterns = [
    path("groups/", GroupCreateView.as_view(), name="group-create"),
]