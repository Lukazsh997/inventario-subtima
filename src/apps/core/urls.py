from django.urls import path

from apps.dashboard.views import home

from . import views

app_name = "core"

urlpatterns = [
    path("", home, name="home"),
    path("buscar/", views.search, name="search"),
    path("health/", views.health, name="health"),
]
