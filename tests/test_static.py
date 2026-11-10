"""O build da imagem roda collectstatic com o armazenamento de produção; um arquivo
referenciado e ausente (ex.: .map do Bootstrap) quebraria o build."""

from django.core.management import call_command


def test_collectstatic_with_production_storage(settings, tmp_path):
    settings.STATIC_ROOT = tmp_path / "static"
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    call_command("collectstatic", interactive=False, verbosity=0)
    assert (tmp_path / "static" / "staticfiles.json").exists()
