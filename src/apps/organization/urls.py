from django.urls import path

from . import views

app_name = "organization"

urlpatterns = [
    path("setores/", views.sector_list, name="sector_list"),
    path("setores/novo/", views.sector_form, name="sector_create"),
    path("setores/<int:pk>/", views.sector_detail, name="sector_detail"),
    path("setores/<int:pk>/editar/", views.sector_form, name="sector_update"),
    path("setores/<int:pk>/ativo/", views.sector_toggle_active, name="sector_toggle_active"),
    path("locais/<int:pk>/ativo/", views.location_toggle_active, name="location_toggle_active"),
    path("servidores/", views.recipient_list, name="recipient_list"),
    path("servidores/novo/", views.recipient_form, name="recipient_create"),
    path("servidores/<int:pk>/editar/", views.recipient_form, name="recipient_update"),
    path("servidores/<int:pk>/ativo/", views.recipient_toggle_active, name="recipient_toggle_active"),
]
