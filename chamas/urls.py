from django.urls import path

from .views import GroupListCreateView,GroupDetailView

urlpatterns = [
    path("groups/", GroupListCreateView.as_view(), name="group-create"),
    path("groups/<slug:slug>/", GroupDetailView.as_view(), name="group-detail"),
]