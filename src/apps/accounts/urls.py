from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("sair/", views.logout_view, name="logout"),
    path("senha/", views.password_change, name="password_change"),
    path("usuarios/", views.user_list, name="user_list"),
    path("usuarios/novo/", views.user_create, name="user_create"),
    path("usuarios/<int:pk>/editar/", views.user_update, name="user_update"),
    path("usuarios/<int:pk>/ativo/", views.user_toggle_active, name="user_toggle_active"),
    path("usuarios/<int:pk>/senha/", views.user_reset_password, name="user_reset_password"),
]
