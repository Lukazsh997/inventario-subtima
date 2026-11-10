from django.db import models


class Role(models.TextChoices):
    ADMIN = "admin", "Administrador"
    TECHNICIAN = "tecnico", "Técnico de TI"
    VIEWER = "consulta", "Consulta"
