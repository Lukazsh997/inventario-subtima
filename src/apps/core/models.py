from django.db import models


class TimeStampedModel(models.Model):
    """Base com datas de criação e de última alteração."""

    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class NumberSequence(models.Model):
    """Contador anual por prefixo (ex.: OP-2026-000123). Use apps.core.numbering.next_number."""

    prefix = models.CharField(max_length=10)
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["prefix", "year"], name="numbersequence_prefix_year_unique")]

    def __str__(self) -> str:
        return f"{self.prefix}-{self.year}: {self.last_value}"
