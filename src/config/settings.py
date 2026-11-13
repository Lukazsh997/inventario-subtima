"""Configurações do Sistema de Patrimônio e Estoque de TI.

Todos os valores sensíveis ou específicos do servidor vêm de variáveis de
ambiente; veja .env.example na raiz do projeto.
"""

from pathlib import Path

from .env import env_bool, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent  # src/

DEBUG = env_bool("DEBUG", False)
SECRET_KEY = env_str("SECRET_KEY", "insecure-dev-key" if DEBUG else None, required=not DEBUG)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
# O HEALTHCHECK do Docker acessa a própria aplicação por 127.0.0.1.
ALLOWED_HOSTS += [host for host in ("127.0.0.1", "localhost") if host not in ALLOWED_HOSTS]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Diretórios persistentes (volumes Docker)
DATA_DIR = Path(env_str("DATA_DIR", str(BASE_DIR.parent / "data")))
MEDIA_ROOT = DATA_DIR / "media"
LOG_DIR = DATA_DIR / "logs"
BACKUP_DIR = Path(env_str("BACKUP_DIR", str(BASE_DIR.parent / "backups")))

ORG_NAME = env_str("ORG_NAME", "Prefeitura Municipal")
ORG_UNIT_NAME = env_str("ORG_UNIT_NAME", "Setor de Tecnologia da Informação")
APP_VERSION = env_str("APP_VERSION", "dev")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.core",
    "apps.audit",
    "apps.accounts",
    "apps.organization",
    "apps.catalog",
    "apps.inventory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
    "apps.accounts.middleware.LoginRequiredMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app_context",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("DB_NAME", "patrimonio"),
        "USER": env_str("DB_USER", "patrimonio"),
        "PASSWORD": env_str("DB_PASSWORD", ""),
        "HOST": env_str("DB_HOST", "localhost"),
        "PORT": env_str("DB_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
        "ATOMIC_REQUESTS": False,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": env_int("PASSWORD_MIN_LENGTH", 10)},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Bloqueio simples contra tentativa de senha por força bruta
LOGIN_MAX_FAILURES = env_int("LOGIN_MAX_FAILURES", 5)
LOGIN_LOCK_MINUTES = env_int("LOGIN_LOCK_MINUTES", 15)

# Sessão e cookies
SESSION_COOKIE_AGE = env_int("SESSION_TIMEOUT_MINUTES", 480) * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
USE_HTTPS = env_bool("USE_HTTPS", False)
SESSION_COOKIE_SECURE = USE_HTTPS
CSRF_COOKIE_SECURE = USE_HTTPS
if USE_HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = env_str("TIME_ZONE", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR.parent / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
MEDIA_URL = "/media/"  # servido apenas por views com controle de acesso

PAGE_SIZE = env_int("PAGE_SIZE", 25)

# Logs: JSON na saída padrão (Portainer) e em arquivo rotativo no volume
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
LOG_TO_FILE = env_bool("LOG_TO_FILE", True)
_handlers = {
    "console": {"class": "logging.StreamHandler", "formatter": "json"},
}
if LOG_TO_FILE:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _handlers["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(LOG_DIR / "app.log"),
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 10,
        "encoding": "utf-8",
        "formatter": "json",
    }
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "config.logging.JsonFormatter"}},
    "handlers": _handlers,
    "root": {"handlers": list(_handlers), "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}

# Usuário administrador criado na primeira subida (comando ensure_admin)
ADMIN_INITIAL_USER = env_str("ADMIN_INITIAL_USER", "")
ADMIN_INITIAL_PASSWORD = env_str("ADMIN_INITIAL_PASSWORD", "")
ADMIN_INITIAL_NAME = env_str("ADMIN_INITIAL_NAME", "Administrador")
