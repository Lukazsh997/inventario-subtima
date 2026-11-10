from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone

from .roles import Role


class AuthSource(models.TextChoices):
    LOCAL = "local", "Local"
    LDAP = "ldap", "LDAP / Active Directory"


class User(AbstractUser):
    """Usuário do sistema (equipe de TI). Quem recebe material é um Recipient."""

    full_name = models.CharField("nome completo", max_length=150)
    role = models.CharField("perfil", max_length=16, choices=Role.choices, default=Role.VIEWER)
    sector = models.ForeignKey(
        "organization.Sector",
        verbose_name="setor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    auth_source = models.CharField(
        "origem da autenticação", max_length=8, choices=AuthSource.choices, default=AuthSource.LOCAL
    )
    failed_login_count = models.PositiveSmallIntegerField(default=0, editable=False)
    locked_until = models.DateTimeField(null=True, blank=True, editable=False)

    objects = UserManager()

    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name"]
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self) -> str:
        return self.full_name or self.username

    def get_full_name(self) -> str:
        return self.full_name or self.username

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > timezone.now()
