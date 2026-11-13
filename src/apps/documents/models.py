from django.conf import settings
from django.db import models
from django.db.models import Q


class ItemKind(models.TextChoices):
    EQUIPMENT = "equipamento", "Equipamentos"
    CONSUMABLE = "consumivel", "Materiais de consumo"


class DocumentTemplate(models.Model):
    """Modelo de termo, versionado.

    Uma versão usada para emitir termos nunca é alterada: editar cria a versão
    seguinte e desativa a anterior, para que todo termo emitido continue
    associado ao texto exato com que foi gerado.
    """

    code = models.SlugField("código", max_length=60, help_text="Identifica o modelo entre as versões")
    version = models.PositiveIntegerField("versão")
    name = models.CharField("nome", max_length=120)
    item_kind = models.CharField("itens", max_length=12, choices=ItemKind.choices)
    operation_types = models.JSONField("tipos de operação", default=list)
    css = models.TextField("estilo (CSS)", blank=True)
    body = models.TextField("conteúdo (HTML com variáveis)")
    active = models.BooleanField("ativa", default=True)
    source = models.CharField(
        "origem do texto",
        max_length=255,
        blank=True,
        help_text="De onde veio o texto institucional (arquivo, data, autorização)",
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["name", "-version"]
        verbose_name = "modelo de termo"
        verbose_name_plural = "modelos de termo"
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="template_code_version_unique"),
            models.UniqueConstraint("code", condition=Q(active=True), name="template_one_active_version"),
        ]

    def __str__(self) -> str:
        return f"{self.name} (v{self.version})"

    @property
    def operation_type_labels(self) -> str:
        from apps.inventory.models import OperationType

        labels = dict(OperationType.choices)
        return ", ".join(labels.get(t, t) for t in self.operation_types)


class DocumentAsset(models.Model):
    """Imagens usadas nos termos (brasão, logotipo), guardadas no banco junto com os termos."""

    key = models.SlugField("chave", max_length=40, unique=True)
    name = models.CharField("descrição", max_length=120)
    content = models.BinaryField("imagem")
    content_type = models.CharField(max_length=40, default="image/png")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.name


class DocumentStatus(models.TextChoices):
    GENERATED = "gerado", "Gerado"
    PRINTED = "impresso", "Impresso"
    AWAITING = "aguardando", "Aguardando assinatura"
    SIGNED = "assinado", "Assinado e recebido pela TI"
    ARCHIVED = "arquivado", "Arquivado"
    CANCELLED = "cancelado", "Cancelado"


STATUS_FLOW = [
    DocumentStatus.GENERATED,
    DocumentStatus.PRINTED,
    DocumentStatus.AWAITING,
    DocumentStatus.SIGNED,
    DocumentStatus.ARCHIVED,
]


class GeneratedDocument(models.Model):
    """Termo emitido. O PDF fica no próprio banco, exatamente como foi gerado (com hash)."""

    number = models.CharField("número do termo", max_length=20, unique=True)
    operation = models.ForeignKey(
        "inventory.StockOperation", verbose_name="operação", on_delete=models.PROTECT, related_name="documents"
    )
    template = models.ForeignKey(
        DocumentTemplate, verbose_name="modelo", on_delete=models.PROTECT, related_name="documents"
    )
    pdf = models.BinaryField("PDF")
    sha256 = models.CharField("SHA-256", max_length=64)
    size = models.PositiveIntegerField("tamanho (bytes)")
    data = models.JSONField("dados preenchidos", default=dict)
    status = models.CharField(
        "situação", max_length=12, choices=DocumentStatus.choices, default=DocumentStatus.GENERATED, db_index=True
    )
    issued_at = models.DateTimeField("emitido em", auto_now_add=True, db_index=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="emitido por", on_delete=models.PROTECT, related_name="+"
    )
    print_count = models.PositiveIntegerField("impressões", default=0)
    replaces = models.OneToOneField(
        "self", verbose_name="substitui", on_delete=models.PROTECT, null=True, blank=True, related_name="replaced_by"
    )

    class Meta:
        ordering = ["-issued_at", "-id"]
        verbose_name = "termo emitido"
        verbose_name_plural = "termos emitidos"

    def __str__(self) -> str:
        return f"{self.number} · {self.template.name}"

    @property
    def filename(self) -> str:
        return f"{self.number}.pdf"


class DocumentStatusChange(models.Model):
    document = models.ForeignKey(GeneratedDocument, on_delete=models.PROTECT, related_name="status_changes")
    from_status = models.CharField(max_length=12, choices=DocumentStatus.choices, blank=True)
    to_status = models.CharField(max_length=12, choices=DocumentStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.CharField("observação", max_length=255, blank=True)

    class Meta:
        ordering = ["changed_at", "id"]

    def __str__(self) -> str:
        return f"{self.document.number}: {self.from_status} → {self.to_status}"
