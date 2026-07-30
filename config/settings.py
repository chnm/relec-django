import mimetypes
import os
from pathlib import Path

import environ
from dotenv import load_dotenv

load_dotenv(verbose=True, override=True)

# Ensure JavaScript files are served with correct MIME type
mimetypes.add_type("application/javascript", ".js", strict=True)
mimetypes.add_type("application/json", ".json", strict=True)

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
    "unfold.contrib.import_export",
    # simple history
    "simple_history",
    # django defaults
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "django.forms",
    # model viz
    "django_dbml",
    # tailwind
    "tailwind",
    "theme",
    # rest framework
    "rest_framework",
    "django_filters",
    # django-tables2
    "django_tables2",
    # cors headers
    "corsheaders",
    # obj storage
    "storages",
    # image processing
    "easy_thumbnails",
    # import/export
    "import_export",
    # local apps
    "religious_ecologies",
    "census",
    "location",
    "pages",
    "analytics",
    "datalayers",
    "visualizations",
]

MIDDLEWARE = [
    "religious_ecologies.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

X_FRAME_OPTIONS = "SAMEORIGIN"

# DEBUG
# ------------------------------------------------------------------------------
# django-debug-toolbar
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
if DEBUG:
    INSTALLED_APPS += ["debug_toolbar"]
    # https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": [
        "debug_toolbar.panels.redirects.RedirectsPanel",
        # Templates panel triggers SynchronousOnlyOperation under Daphne/ASGI
        # when it tries to repr() querysets in template context
        "debug_toolbar.panels.templates.TemplatesPanel",
    ],
    "SHOW_TEMPLATE_CONTEXT": True,
}

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
                "pages.context_processors.navigation_pages",
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
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECK": True,
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
    "django.contrib.auth.backends.ModelBackend",
]


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
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Storage backend configuration for both default and staticfiles storage
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
# Only aliases that templates actually render — every alias here is
# generated for every uploaded image (saved_file signal +
# generate_thumbnails command), and adding one later means re-downloading
# every original to backfill it.
THUMBNAIL_ALIASES = {
    "": {
        "medium": {"size": (400, 300), "crop": False},  # census browser list
        "large": {"size": (800, 600), "crop": False},  # record detail page
    },
}

# Django Unfold Configuration
UNFOLD = {
    "SITE_TITLE": "Religious Ecologies",
    "SITE_HEADER": "Religious Ecologies",
    "SITE_URL": "/",
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
                "title": "Analytics & Reporting",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Analytics Home",
                        "icon": "analytics",
                        "link": lambda request: "/analytics/",
                    },
                    {
                        "title": "Query Builder",
                        "icon": "search",
                        "link": lambda request: "/analytics/query/",
                    },
                    {
                        "title": "Denomination Analysis",
                        "icon": "bar_chart",
                        "link": lambda request: "/analytics/analysis/denominations/",
                    },
                    {
                        "title": "Location Analysis",
                        "icon": "map",
                        "link": lambda request: "/analytics/analysis/locations/",
                    },
                    {
                        "title": "Data Completeness",
                        "icon": "checklist",
                        "link": lambda request: "/analytics/analysis/completeness/",
                    },
                    {
                        "title": "Export by Location",
                        "icon": "download",
                        "link": lambda request: "/admin/census/censusschedule/location-export/",
                    },
                ],
            },
            {
                "title": "Transcriptions",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Census Schedules",
                        "icon": "description",
                        "link": lambda request: "/admin/census/censusschedule/",
                    },
                    {
                        "title": "Review Queue",
                        "icon": "rate_review",
                        "link": lambda request: "/admin/census/censusschedule/?workflow_view=review_queue",
                    },
                    {
                        "title": "Imported - Needs Review",
                        "icon": "fact_check",
                        "link": lambda request: "/admin/census/censusschedule/?workflow_view=needs_review",
                    },
                    {
                        "title": "Student Work - Ready",
                        "icon": "assignment_turned_in",
                        "link": lambda request: "/admin/census/censusschedule/?workflow_view=completed",
                    },
                    {
                        "title": "Assigned to Me",
                        "icon": "assignment_ind",
                        "link": lambda request: "/admin/census/censusschedule/?workflow_view=assigned_to_me",
                    },
                    {
                        "title": "Religious Bodies",
                        "icon": "account_balance",
                        "link": lambda request: "/admin/census/religiousbody/",
                    },
                    {
                        "title": "Denominations",
                        "icon": "category",
                        "link": lambda request: "/admin/census/denomination/",
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
                    {
                        "title": "Missing Location",
                        "icon": "wrong_location",
                        "link": lambda request: "/admin/census/censusschedule/?schedule_location_status=missing_location",
                    },
                ],
            },
            {
                "title": "Location Data",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "States",
                        "icon": "flag",
                        "link": lambda request: "/admin/location/state/",
                    },
                    {
                        "title": "Counties",
                        "icon": "map",
                        "link": lambda request: "/admin/location/county/",
                    },
                    {
                        "title": "Populated Places",
                        "icon": "location_city",
                        "link": lambda request: "/admin/location/populatedplace/",
                    },
                ],
            },
            {
                "title": "Content Management",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Blog Posts",
                        "icon": "article",
                        "link": lambda request: "/admin/pages/blogpost/",
                    },
                    {
                        "title": "Pages",
                        "icon": "article",
                        "link": lambda request: "/admin/pages/page/",
                    },
                    {
                        "title": "Visualizations",
                        "icon": "article",
                        "link": lambda request: "/admin/visualizations/visualization/",
                    },
                    {
                        "title": "Data Layer Points",
                        "icon": "layers",
                        "link": lambda request: "/admin/datalayers/datalayer/",
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
        lambda request: "/static/css/custom_unfold.css",
    ],
}

# Geocoding settings
# ------------------------------------------------------------------------------
GEOCODING_USER_AGENT = "ReligiousEcologies/1.0 (Django Historical Census Project)"

# CORS Configuration
# ------------------------------------------------------------------------------
# The API is read-only and public, so allow all origins.
CORS_ALLOW_ALL_ORIGINS = True
CORS_URLS_REGEX = r"^/census/api/.*$"

# Cache Configuration
# ------------------------------------------------------------------------------
# Uses Memcached in production (via MEMCACHED_URL env var).
# Falls back to in-memory cache for local development.
MEMCACHED_URL = env("MEMCACHED_URL", default="")

if MEMCACHED_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.memcached.PyMemcacheCache",
            "LOCATION": MEMCACHED_URL,
            "TIMEOUT": 900,  # Default 15-minute cache timeout
            "OPTIONS": {
                "no_delay": True,
                "ignore_exc": True,  # Return cache miss on errors, don't crash
                "connect_timeout": 3,
                "timeout": 3,
                "use_pooling": True,
            },
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "TIMEOUT": 900,
        }
    }

# Django REST Framework Configuration
# ------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,  # Default page size
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",  # Make API publicly readable
    ],
}
