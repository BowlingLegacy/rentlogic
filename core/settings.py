import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().strip('"').strip("'").lower()
    return normalized in {"1", "true", "yes", "on"}


# ---------------------------------------------------------
# SECURITY
# ---------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
DEBUG = env_bool("DEBUG")
DEMO_MODE = env_bool("DEMO_MODE")
RENTAL_LEDGER_SITE = env_bool("RENTAL_LEDGER_SITE")
DEMO_SESSION_SECONDS = int(os.environ.get("DEMO_SESSION_SECONDS", "7200"))
DEMO_ADMIN_USERNAME = os.environ.get("DEMO_ADMIN_USERNAME", "demo-admin")
DEMO_PUBLIC_URL = os.environ.get("DEMO_PUBLIC_URL", "").strip()
APP_STORE_URL = os.environ.get("APP_STORE_URL", "").strip()
GOOGLE_PLAY_URL = os.environ.get("GOOGLE_PLAY_URL", "").strip()

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "bowlinglegacy.com",
    "www.bowlinglegacy.com",
    "rentalledgerpro.com",
    "www.rentalledgerpro.com",
    "rentlogic-1.onrender.com",
    "rentlogic-cly7.onrender.com",
]
ALLOWED_HOSTS.extend([
    host.strip()
    for host in os.environ.get("DEMO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
])
ALLOWED_HOSTS.extend([
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "").split(",")
    if host.strip()
])

# ---------------------------------------------------------
# STRIPE
# ---------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLIC_KEY = os.environ.get("STRIPE_PUBLIC_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# ---------------------------------------------------------
# CUSTOM USER MODEL
# ---------------------------------------------------------
AUTH_USER_MODEL = "main.User"

# ---------------------------------------------------------
# APPLICATIONS
# ---------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "main",
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

ROOT_URLCONF = "core.urls"

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
                "main.context_processors.demo_mode",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# ---------------------------------------------------------
# DATABASE — RENDER POSTGRES WITH SSL REQUIRED
# ---------------------------------------------------------
if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB"),
            "USER": os.environ.get("POSTGRES_USER"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
            "HOST": os.environ.get("POSTGRES_HOST"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "OPTIONS": {
                "sslmode": "require",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------------------------------------------------------
# PASSWORD VALIDATION
# ---------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_RESET_TIMEOUT = int(os.environ.get("PASSWORD_RESET_TIMEOUT", "1800"))

# ---------------------------------------------------------
# INTERNATIONALIZATION
# ---------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------
# STATIC FILES
# ---------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ---------------------------------------------------------
# MEDIA FILES
# ---------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ---------------------------------------------------------
# EMAIL SETTINGS
# ---------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.office365.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")

DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER,
)
RENTAL_LEDGER_LEAD_EMAIL = os.environ.get("RENTAL_LEDGER_LEAD_EMAIL", "michael@bowlinglegacy.com")

if DEMO_MODE:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    SESSION_COOKIE_AGE = DEMO_SESSION_SECONDS
    SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ---------------------------------------------------------
# SMS SETTINGS
# ---------------------------------------------------------
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "twilio").strip().lower()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
TELNYX_API_KEY = os.environ.get("TELNYX_API_KEY", "")
TELNYX_FROM_NUMBER = os.environ.get("TELNYX_FROM_NUMBER", "")

# ---------------------------------------------------------
# RECEIPT OCR SETTINGS
# ---------------------------------------------------------
RECEIPT_OCR_PROVIDER = os.environ.get("RECEIPT_OCR_PROVIDER", "").strip().lower()
OCR_SPACE_API_KEY = os.environ.get("OCR_SPACE_API_KEY", "")
OCR_SPACE_ENDPOINT = os.environ.get("OCR_SPACE_ENDPOINT", "https://api.ocr.space/parse/image")
OCR_SPACE_LANGUAGE = os.environ.get("OCR_SPACE_LANGUAGE", "eng")

# ---------------------------------------------------------
# MICROSOFT GRAPH MAILBOX SETTINGS
# ---------------------------------------------------------
MICROSOFT_GRAPH_CLIENT_ID = os.environ.get("MICROSOFT_GRAPH_CLIENT_ID", "")
MICROSOFT_GRAPH_CLIENT_SECRET = os.environ.get("MICROSOFT_GRAPH_CLIENT_SECRET", "")
MICROSOFT_GRAPH_TENANT_ID = os.environ.get("MICROSOFT_GRAPH_TENANT_ID", "common")
MICROSOFT_GRAPH_REDIRECT_URI = os.environ.get("MICROSOFT_GRAPH_REDIRECT_URI", "")
MICROSOFT_GRAPH_MAILBOX_USER = os.environ.get("MICROSOFT_GRAPH_MAILBOX_USER", EMAIL_HOST_USER or "")

# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------
import logging
logging.basicConfig(level=logging.DEBUG)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/tenant-dashboard/"
LOGOUT_REDIRECT_URL = "/"
