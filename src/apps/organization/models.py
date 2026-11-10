from django.db import models
from django.db.models.functions import Lower

from apps.core.models import TimeStampedModel


class Sector(TimeStampedModel):
    """Secretaria, subsecretaria, departamento ou setor do órgão.

    Setores com histórico nunca são apagados nem renomeados retroativamente:
    são desativados, e os termos guardam o nome vigente na emissão.
    """

    name = models.CharField("nome", max_length=200)
    acronym = models.CharField("sigla", max_length=30, blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name="vinculado a",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "setor"
        verbose_name_plural = "setores"
        constraints = [
            models.UniqueConstraint(Lower("name"), name="sector_name_unique_ci"),
            models.CheckConstraint(condition=~models.Q(parent=models.F("pk")), name="sector_not_own_parent"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.acronym})" if self.acronym else self.name

    def ancestors(self) -> list["Sector"]:
        chain, node, seen = [], self.parent, {self.pk}
        while node is not None and node.pk not in seen:
            chain.append(node)
            seen.add(node.pk)
            node = node.parent
        return chain

    @property
    def path(self) -> str:
        names = [s.acronym or s.name for s in reversed(self.ancestors())]
        return " › ".join([*names, self.acronym or self.name])


class Location(TimeStampedModel):
    """Local físico (prédio, andar, sala) onde um equipamento pode estar."""

    sector = models.ForeignKey(Sector, verbose_name="setor", on_delete=models.PROTECT, related_name="locations")
    name = models.CharField("descrição", max_length=200, help_text="Ex.: Prédio sede, 2º andar, sala 204")
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["sector__name", "name"]
        verbose_name = "local"
        verbose_name_plural = "locais"
        constraints = [
            models.UniqueConstraint("sector", Lower("name"), name="location_unique_per_sector_ci"),
        ]

    def __str__(self) -> str:
        return f"{self.name} — {self.sector.acronym or self.sector.name}"


class Recipient(TimeStampedModel):
    """Servidor que recebe e assina os termos. Não precisa ter login no sistema."""

    full_name = models.CharField("nome completo", max_length=200)
    registration = models.CharField("matrícula", max_length=30, null=True, blank=True)
    job_title = models.CharField("cargo/função", max_length=120, blank=True)
    sector = models.ForeignKey(Sector, verbose_name="setor", on_delete=models.PROTECT, related_name="recipients")
    phone = models.CharField("telefone/ramal", max_length=40, blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "servidor"
        verbose_name_plural = "servidores"
        constraints = [
            models.UniqueConstraint(
                "registration",
                name="recipient_registration_unique",
                condition=models.Q(registration__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} (mat. {self.registration})" if self.registration else self.full_name
