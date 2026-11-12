from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("contas/", include("apps.accounts.urls")),
    path("organizacao/", include("apps.organization.urls")),
    path("auditoria/", include("apps.audit.urls")),
    path("estoque/", include("apps.catalog.urls")),
    path("estoque/", include("apps.inventory.urls")),
]

handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
