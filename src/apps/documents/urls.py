from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("<int:pk>/", views.document_detail, name="detail"),
    path("<int:pk>/pdf/", views.document_pdf, name="pdf"),
    path("<int:pk>/situacao/", views.document_status, name="status"),
    path("<int:pk>/reemitir/", views.document_reissue, name="reissue"),
    path("operacao/<int:pk>/gerar/", views.issue_for_operation, name="issue_for_operation"),
    path("modelos/", views.template_list, name="template_list"),
    path("modelos/novo/", views.template_edit, name="template_create"),
    path("modelos/<int:pk>/nova-versao/", views.template_edit, name="template_edit"),
    path("modelos/<int:pk>/previa/", views.template_preview, name="template_preview"),
    path("modelos/<int:pk>/ativo/", views.template_toggle, name="template_toggle"),
    path("imagens/<slug:key>/", views.asset_image, name="asset_image"),
    path("imagens/<slug:key>/substituir/", views.asset_upload, name="asset_upload"),
]
