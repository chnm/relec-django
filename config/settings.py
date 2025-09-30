import os
from pathlib import Path

import environ
from dotenv import load_dotenv

load_dotenv(verbose=True, override=True)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
env = environ.Env()
READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=True)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

env = environ.FileAwareEnv(
    DEBUG=(bool, False),
)

# GENERAL
# ------------------------------------------------------------------------------

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="django-insecure-wu9#po37gfc6e$9bg#qt&fqk42+flc8zp^4xj)(=etm@_lg%#8",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", default=["http://localhost"]
)

# Application definition

INSTALLED_APPS = [
    "daphne",
    # django-unfold
    "unfold",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.simple_history",
    # simple history
    "simple_history",
    # django defaults
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
    # model viz
    "django_dbml",
    # allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.github",
    # tailwind
    "tailwind",
    "theme",
    # rest framework
    "rest_framework",
    "django_filters",
    # obj storage
    "storages",
    # image processing
    "easy_thumbnails",
    # local apps
    "religious_ecologies",
    "census",
    "location",
    "pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # allauth
    "allauth.account.middleware.AccountMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

X_FRAME_OPTIONS = "SAMEORIGIN"

# DEBUG
# ------------------------------------------------------------------------------
# django-debug-toolbar
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405
# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config

ROOT_URLCONF = "config.urls"

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
                # pages context processor for navigation
                "pages.views.nav_pages_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
        "NAME": env("DB_NAME", default="religious_ecologies"),
        "USER": env("DB_USER", default="religious_ecologies"),
        "PASSWORD": env("DB_PASS", default="password"),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",
    # allauth specific authentication methods, such as login by email
    "allauth.account.auth_backends.AuthenticationBackend",
]


# allauth: provider specific settings
SOCIALACCOUNT_PROVIDERS = {
    "github": {
        "VERIFIED_EMAIL": True,
        "APP": {
            "client_id": env("ALLAUTH_GITHUB_CLIENT_ID", default="PLACEHOLDER"),
            "secret": env("ALLAUTH_GITHUB_CLIENT_SECRET", default="PLACEHOLDER"),
        },
    }
}


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"

USE_I18N = True
USE_TZ = True
# Theme
TAILWIND_APP_NAME = "theme"
INTERNAL_IPS = [
    "127.0.0.1",
]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/
STATIC_URL = "static/"
STATICFILES_DIRS = (os.path.join(BASE_DIR, "static"),)
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Storage backend
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Media files
OBJ_STORAGE = env("OBJ_STORAGE", default=False)
if OBJ_STORAGE:
    AWS_ACCESS_KEY_ID = env("OBJ_STORAGE_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("OBJ_STORAGE_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("OBJ_STORAGE_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = env("OBJ_STORAGE_ENDPOINT_URL")

    MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/"

    # override default storage backend for media
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
    }
else:
    MEDIA_URL = "media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "mediafiles")

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Easy Thumbnails Configuration
THUMBNAIL_ALIASES = {
    "": {
        "admin_thumbnail": {"size": (100, 75), "crop": True},
        "small": {"size": (200, 150), "crop": True},
        "medium": {"size": (400, 300), "crop": False},
        "large": {"size": (800, 600), "crop": False},
    },
}

# Django Unfold Configuration
UNFOLD = {
    "SITE_TITLE": "Religious Ecologies",
    "SITE_HEADER": "",
    "SITE_URL": "/",
    "SITE_ICON": {
        "light": lambda request: "/static/images/logo.svg",
        "dark": lambda request: "/static/images/logo.svg",
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Dashboard",
                "separator": True,
                "items": [
                    {
                        "title": "Overview",
                        "icon": "dashboard",
                        "link": lambda request: "/admin/",
                    },
                ],
            },
            {
                "title": "Data Quality",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Schedule ID Gaps",
                        "icon": "dangerous",
                        "link": lambda request: "/admin/census/censusschedule/schedule-gap-analysis/",
                    },
                    {
                        "title": "Missing Counties",
                        "icon": "place",
                        "link": lambda request: "/admin/census/censusschedule/missing-county-analysis/",
                    },
                ],
            },
            {
                "title": "Transcription Project",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Census Schedules",
                        "icon": "description",
                        "link": lambda request: "/admin/census/censusschedule/",
                    },
                    {
                        "title": "Religious Bodies",
                        "icon": "account_balance",
                        "link": lambda request: "/admin/census/religiousbody/",
                    },
                    {
                        "title": "Membership Data",
                        "icon": "people",
                        "link": lambda request: "/admin/census/membership/",
                    },
                    {
                        "title": "Clergy Information",
                        "icon": "person",
                        "link": lambda request: "/admin/census/clergy/",
                    },
                ],
            },
            {
                "title": "Reference Data",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Denominations",
                        "icon": "category",
                        "link": lambda request: "/admin/census/denomination/",
                    },
                    {
                        "title": "Locations",
                        "icon": "place",
                        "link": lambda request: "/admin/location/location/",
                    },
                ],
            },
            {
                "title": "Content Management",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Pages",
                        "icon": "article",
                        "link": lambda request: "/admin/pages/page/",
                    },
                ],
            },
            {
                "title": "System Administration",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": lambda request: "/admin/auth/user/",
                    },
                    {
                        "title": "Groups",
                        "icon": "group",
                        "link": lambda request: "/admin/auth/group/",
                    },
                    {
                        "title": "User Sessions",
                        "icon": "vpn_key",
                        "link": lambda request: "/admin/sessions/session/",
                    },
                ],
            },
        ],
    },
    "TABS": [
        {
            "models": [
                "census.censusschedule",
                "census.religiousbody",
                "census.membership",
                "census.clergy",
            ],
            "items": [
                {
                    "title": "Census Schedules",
                    "link": lambda request: "/admin/census/censusschedule/",
                },
                {
                    "title": "Religious Bodies",
                    "link": lambda request: "/admin/census/religiousbody/",
                },
                {
                    "title": "Membership",
                    "link": lambda request: "/admin/census/membership/",
                },
                {
                    "title": "Clergy",
                    "link": lambda request: "/admin/census/clergy/",
                },
            ],
        }
    ],
    "COLORS": {
        "primary": {
            "50": "#eff6ff",
            "100": "#dbeafe",
            "200": "#bfdbfe",
            "300": "#93c5fd",
            "400": "#60a5fa",
            "500": "#0060b1",  # RelEco blue
            "600": "#0052a3",
            "700": "#004494",
            "800": "#003685",
            "900": "#002876",
            "950": "#001a5e",
        }
    },
    "STYLES": [
        lambda request: "css/custom_unfold.css",
    ],
}
