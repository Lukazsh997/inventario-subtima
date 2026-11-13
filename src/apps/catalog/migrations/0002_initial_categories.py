"""Categorias iniciais: as do documento de requisitos (seções 3.1 e 3.2) e Estabilizadores,
que aparecem nas etiquetas e no termo de transferência do órgão."""

from django.db import migrations

EQUIPMENT = [
    "Computadores desktop", "Notebooks", "Monitores", "Servidores", "Teclados", "Mouses", "Nobreaks",
    "Estabilizadores", "Impressoras", "Scanners", "Switches", "Roteadores", "Access Points",
    "Outros equipamentos de informática",
]
CONSUMABLE = [
    "Toners de impressora", "Papel A4", "Cartuchos de tinta", "Cabos de rede", "Conectores RJ45",
    "Pilhas e baterias", "Outros materiais de consumo",
]


def create(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for name in EQUIPMENT:
        Category.objects.get_or_create(name=name, kind="equipamento")
    for name in CONSUMABLE:
        Category.objects.get_or_create(name=name, kind="consumivel")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [migrations.RunPython(create, migrations.RunPython.noop)]
