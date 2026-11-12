from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("ler/", views.scan, name="scan"),
    path("equipamentos/", views.equipment_list, name="equipment_list"),
    path("equipamentos/nova-entrada/", views.equipment_create, name="equipment_create"),
    path("equipamentos/importar/", views.import_equipment, name="equipment_import"),
    path("equipamentos/importar/modelo.csv", views.import_template, name="equipment_import_template"),
    path("equipamentos/<int:pk>/", views.equipment_detail, name="equipment_detail"),
    path("equipamentos/<int:pk>/editar/", views.equipment_update, name="equipment_update"),
    path("api/equipamentos/", views.equipment_lookup, name="equipment_lookup"),
    path("materiais/", views.consumable_list, name="consumable_list"),
    path("materiais/novo/", views.consumable_form, name="consumable_create"),
    path("materiais/<int:pk>/", views.consumable_detail, name="consumable_detail"),
    path("materiais/<int:pk>/editar/", views.consumable_form, name="consumable_update"),
    path("materiais/<int:pk>/ativo/", views.consumable_toggle_active, name="consumable_toggle_active"),
    path("categorias/", views.category_list, name="category_list"),
    path("categorias/nova/", views.category_form, name="category_create"),
    path("categorias/<int:pk>/editar/", views.category_form, name="category_update"),
    path("categorias/<int:pk>/ativo/", views.category_toggle_active, name="category_toggle_active"),
]
