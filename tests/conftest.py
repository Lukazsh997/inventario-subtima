import os

import pytest

# Ambiente de teste: banco PostgreSQL real (as regras de integridade dependem dele).
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_TO_FILE", "false")
os.environ.setdefault("DB_PASSWORD", "patrimonio")

from apps.accounts.roles import Role  # noqa: E402

PASSWORD = "Senha-de-teste-2026"


@pytest.fixture(autouse=True)
def _media_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def make_user(db, django_user_model):
    def factory(username: str, role: str = Role.TECHNICIAN, **extra):
        user = django_user_model(
            username=username, full_name=extra.pop("full_name", username.title()), role=role, **extra
        )
        user.set_password(PASSWORD)
        user.save()
        return user

    return factory


@pytest.fixture
def admin_user(make_user):
    return make_user("admin", Role.ADMIN)


@pytest.fixture
def tech_user(make_user):
    return make_user("tecnico", Role.TECHNICIAN)


@pytest.fixture
def viewer_user(make_user):
    return make_user("consulta", Role.VIEWER)


@pytest.fixture
def client_for(client):
    def login(user):
        client.force_login(user)
        return client

    return login
