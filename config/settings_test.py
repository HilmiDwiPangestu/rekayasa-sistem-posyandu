"""Settings khusus unit/integration test.

Selalu menggunakan SQLite terisolasi agar test tidak bergantung pada PostgreSQL
atau kredensial yang ada di .env development.
"""

from .settings import *  # noqa: F403,F401

DEBUG = False
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = []
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
