from django.urls import path

from . import views

app_name = "alerts"

urlpatterns = [
    path("", views.critical_list, name="critical_list"),
]
