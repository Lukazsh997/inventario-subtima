from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("operacoes/", views.operation_list, name="operation_list"),
    path("operacoes/<int:pk>/", views.operation_detail, name="operation_detail"),
    path("operacoes/<int:pk>/estornar/", views.operation_reverse, name="operation_reverse"),
    path("operacoes/equipamentos/nova/", views.equipment_operation, name="equipment_operation"),
    path("operacoes/materiais/nova/", views.consumable_operation, name="consumable_operation"),
    path("api/setor/", views.sector_options, name="sector_options"),
]
