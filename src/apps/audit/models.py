from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LOGIN = "login", "Login"
    LOGIN_FAILED = "login_failed", "Falha de login"
    LOGOUT = "logout", "Logout"
    CREATE = "create", "Criação"
    UPDATE = "update", "Alteração"
    DEACTIVATE = "deactivate", "Desativação"
    REACTIVATE = "reactivate", "Reativação"
    PASSWORD_CHANGE = "password_change", "Troca de senha"
    PASSWORD_RESET = "password_reset", "Redefinição de senha"
    OPERATION = "operation", "Movimentação"
    REVERSAL = "reversal", "Estorno"


class AuditLog(models.Model):
    """Registro de auditoria. Somente inserção: o banco rejeita UPDATE e DELETE."""

    created_at = models.DateTimeField("data/hora", auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    username = models.CharField("login", max_length=150, blank=True)
    action = models.CharField("ação", max_length=32, choices=AuditAction.choices, db_index=True)
    entity = models.CharField("entidade", max_length=64, blank=True, db_index=True)
    entity_id = models.CharField("identificador", max_length=64, blank=True)
    summary = models.CharField("resumo", max_length=255, blank=True)
    changes = models.JSONField("alterações", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        indexes = [models.Index(fields=["entity", "entity_id"])]

    def __str__(self) -> str:
        return f"{self.created_at:%d/%m/%Y %H:%M} {self.username} {self.get_action_display()}"
