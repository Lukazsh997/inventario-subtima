from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.services import ensure_initial_admin


class Command(BaseCommand):
    help = "Cria o administrador inicial (ADMIN_INITIAL_USER/PASSWORD) se ainda não houver usuários."

    def handle(self, *args, **options):
        user = ensure_initial_admin(
            username=settings.ADMIN_INITIAL_USER,
            password=settings.ADMIN_INITIAL_PASSWORD,
            full_name=settings.ADMIN_INITIAL_NAME,
        )
        if user:
            self.stdout.write(self.style.SUCCESS(f"Administrador inicial criado: {user.username}"))
        else:
            self.stdout.write("Administrador inicial não criado (já existem usuários ou variáveis não definidas).")
