from django.db import models


class TimeStampedModel(models.Model):
    """Base com datas de criação e de última alteração."""

    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True
