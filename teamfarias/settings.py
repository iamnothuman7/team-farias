"""
Configurações do projeto Team Farias — Plataforma de gestão esportiva.

Variáveis de ambiente são carregadas de um arquivo .env na raiz do projeto
(veja .env.example). Nenhum segredo é obrigatório em desenvolvimento.
"""

from pathlib import Path
import os
import sys

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TESTING = "test" in sys.argv


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "sim", "yes", "on"}


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-desenvolvimento-team-farias-troque-em-producao",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# Em desenvolvimento, o servidor roda em portas variadas.
if DEBUG:
    ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "accounts",
    "school",
    "billing",
    "dashboard",
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
]

ROOT_URLCONF = "teamfarias.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "teamfarias.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / os.getenv("DJANGO_DB_NAME", "db.sqlite3"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Fortaleza"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Em desenvolvimento/testes não há manifesto de collectstatic: usa storage sem hash.
if DEBUG or TESTING:
    STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:redirect"
LOGOUT_REDIRECT_URL = "core:home"

# ---------------------------------------------------------------- Marca / site
SITE_NAME = "Team Farias"
SITE_TAGLINE = "Vôlei de Praia"
SITE_PHONE = os.getenv("SITE_PHONE", "(85) 90000-0000")
SITE_WHATSAPP = os.getenv("SITE_WHATSAPP", "5585900000000")
SITE_EMAIL = os.getenv("SITE_EMAIL", "contato@teamfarias.com.br")
SITE_INSTAGRAM = os.getenv("SITE_INSTAGRAM", "teamfarias")
SITE_CITY = os.getenv("SITE_CITY", "Fortaleza")
SITE_STATE = os.getenv("SITE_STATE", "CE")
SITE_ADDRESS = os.getenv("SITE_ADDRESS", "Quadra de areia — Beira-Mar, Fortaleza/CE")
SITE_PIX_KEY = os.getenv("SITE_PIX_KEY", "contato@teamfarias.com.br")

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = "DENY"
