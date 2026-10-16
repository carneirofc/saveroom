import importlib
import json
import os
import re
from datetime import timedelta
from decimal import Decimal
from ipaddress import ip_network
from pathlib import Path
from urllib.parse import urljoin, urlparse

from django.core.exceptions import ImproperlyConfigured

import dj_database_url
from corsheaders.defaults import default_headers

from baserow.config.settings.utils import (
    Setting,
    crontab,
    get_crontab_from_env,
    read_file,
    set_settings_from_env_if_present,
    str_to_bool,
    try_float,
    try_int,
)
from baserow.core.telemetry.utils import otel_is_enabled
from baserow.throttling.types import RateLimit
from baserow.version import VERSION

# Build metadata, injected as docker build args when an image is published. They
# identify the exact source the running instance was built from, which the version
# number alone cannot: VERSION tracks the upstream Baserow codebase, while these
# track this fork's release tag and commit. Empty in a development checkout.
BASEROW_BUILD_VERSION = os.getenv("BASEROW_BUILD_VERSION", "")
BASEROW_BUILD_COMMIT = os.getenv("BASEROW_BUILD_COMMIT", "")
BASEROW_BUILD_DATE = os.getenv("BASEROW_BUILD_DATE", "")

# A comma separated list of feature flags used to enable in-progress or not ready
# features for developers. See docs/development/feature-flags.md for more info.
FEATURE_FLAGS = [
    flag.strip().lower() for flag in os.getenv("FEATURE_FLAGS", "").split(",")
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASEROW_PLUGIN_DIR_PATH = Path(os.environ.get("BASEROW_PLUGIN_DIR", "/baserow/plugins"))

if BASEROW_PLUGIN_DIR_PATH.exists():
    BASEROW_PLUGIN_FOLDERS = [
        file
        for file in BASEROW_PLUGIN_DIR_PATH.iterdir()
        if file.is_dir() and Path(file, "backend").exists()
    ]
else:
    BASEROW_PLUGIN_FOLDERS = []

BASEROW_BACKEND_PLUGIN_NAMES = [d.name for d in BASEROW_PLUGIN_FOLDERS]
# This fork ships no built-in plugins. Third party plugins are still discovered
# through BASEROW_PLUGIN_DIR above.
BASEROW_BUILT_IN_PLUGINS = []

# SECURITY WARNING: keep the secret key used in production secret!
if "SECRET_KEY" in os.environ:
    SECRET_KEY = os.environ.get("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("BASEROW_BACKEND_DEBUG", "off") == "on"

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
ALLOWED_HOSTS += os.getenv("BASEROW_EXTRA_ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "drf_spectacular",
    "djcelery_email",
    "health_check",
    "health_check.db",
    "health_check.cache",
    "health_check.contrib.migrations",
    "health_check.contrib.redis",
    "health_check.contrib.celery_ping",
    "health_check.contrib.psutil",
    "health_check.contrib.s3boto3_storage",
    "baserow.core",
    "baserow.api",
    "baserow.ws",
    "baserow.contrib.database",
    "baserow.contrib.integrations",
    "baserow.contrib.builder",
    "baserow.contrib.dashboard",
    "baserow.contrib.automation",
    *BASEROW_BUILT_IN_PLUGINS,
]


ADDITIONAL_APPS = os.getenv("ADDITIONAL_APPS", "").split(",")
if ADDITIONAL_APPS is not None:
    INSTALLED_APPS += [app.strip() for app in ADDITIONAL_APPS if app.strip() != ""]

if BASEROW_BACKEND_PLUGIN_NAMES:
    print(f"Loaded backend plugins: {','.join(BASEROW_BACKEND_PLUGIN_NAMES)}")
    INSTALLED_APPS.extend(BASEROW_BACKEND_PLUGIN_NAMES)

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "baserow.core.cache.LocalCacheMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "baserow.api.user_sources.middleware.AddUserSourceUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "baserow.middleware.BaserowCustomHttp404Middleware",
    "baserow.middleware.ClearContextMiddleware",
    "baserow.middleware.ClearDBStateMiddleware",
]

if otel_is_enabled():
    MIDDLEWARE += ["baserow.core.telemetry.middleware.BaserowOTELMiddleware"]

ROOT_URLCONF = "baserow.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "baserow.config.wsgi.application"
ASGI_APPLICATION = "baserow.config.asgi.application"


# `ASGI_HTTP_MAX_CONCURRENCY` sets max concurrent asgi requests to be processed by
# the asgi application. It's configurable with `BASEROW_ASGI_HTTP_MAX_CONCURRENCY`
# env variable.
# The default is None - no concurrency limit
ASGI_HTTP_MAX_CONCURRENCY = (
    int(os.getenv("BASEROW_ASGI_HTTP_MAX_CONCURRENCY") or 0) or None
)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_USERNAME = os.getenv("REDIS_USER", "")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_PROTOCOL = os.getenv("REDIS_PROTOCOL", "redis")
REDIS_SSL_CERT_REQS = os.getenv("REDIS_SSL_CERT_REQS", "required")
REDIS_SSL_CA_CERTS = os.getenv("REDIS_SSL_CA_CERTS", "")

redis_auth = f"{REDIS_USERNAME}:{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
redis_url_suffix = ""
if REDIS_PROTOCOL == "rediss":
    redis_url_suffix = f"?ssl_cert_reqs={REDIS_SSL_CERT_REQS}"
    if REDIS_SSL_CA_CERTS:
        redis_url_suffix += f"&ssl_ca_certs={REDIS_SSL_CA_CERTS}"

REDIS_URL = os.getenv(
    "REDIS_URL",
    f"{REDIS_PROTOCOL}://{redis_auth}{REDIS_HOST}:{REDIS_PORT}/0{redis_url_suffix}",
)

BASEROW_GROUP_STORAGE_USAGE_QUEUE = os.getenv(
    "BASEROW_GROUP_STORAGE_USAGE_QUEUE", "export"
)
BASEROW_ROLE_USAGE_QUEUE = os.getenv("BASEROW_GROUP_STORAGE_USAGE_QUEUE", "export")

CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_ROUTES = {
    "baserow.contrib.database.export.tasks.run_export_job": {"queue": "export"},
    "baserow.contrib.database.export.tasks.clean_up_old_jobs": {"queue": "export"},
    "baserow.core.trash.tasks.mark_old_trash_for_permanent_deletion": {
        "queue": "export"
    },
    "baserow.core.trash.tasks.permanently_delete_marked_trash": {"queue": "export"},
    "baserow.core.usage.tasks": {"queue": BASEROW_GROUP_STORAGE_USAGE_QUEUE},
    "baserow.contrib.database.table.tasks.run_row_count_job": {"queue": "export"},
    "baserow.core.jobs.tasks.clean_up_jobs": {"queue": "export"},
    "baserow.core.backups.tasks.run_due_backup_schedules": {"queue": "export"},
    "baserow.core.backups.tasks.apply_backup_retention": {"queue": "export"},
}
CELERY_TASK_SOFT_TIME_LIMIT = int(
    os.getenv("CELERY_TASK_SOFT_TIME_LIMIT") or 60 * 5
)  # default 5 minutes
CELERY_TASK_TIME_LIMIT = CELERY_TASK_SOFT_TIME_LIMIT + 60  # default 6 minutes

CELERY_REDBEAT_REDIS_URL = REDIS_URL
# Explicitly set the same value as the default loop interval here so we can use it
# later. CELERY_BEAT_MAX_LOOP_INTERVAL < CELERY_REDBEAT_LOCK_TIMEOUT must be kept true
# as otherwise a beat instance will acquire the lock, do scheduling, go to sleep for
# CELERY_BEAT_MAX_LOOP_INTERVAL before waking up where it assumes it still owns the lock
# however if the lock timeout is less than the interval the lock will have been released
# and the beat instance will crash as it attempts to extend the lock which it no longer
# owns.
CELERY_BEAT_MAX_LOOP_INTERVAL = os.getenv("CELERY_BEAT_MAX_LOOP_INTERVAL", 20)
# By default CELERY_REDBEAT_LOCK_TIMEOUT = 5 * CELERY_BEAT_MAX_LOOP_INTERVAL
# Only one beat instance can hold this lock and schedule tasks at any one time.
# This means if one celery-beat instance crashes any other replicas waiting to take over
# will by default wait 25 minutes until the lock times out and they can acquire
# the lock to start scheduling tasks again.
# Instead we just set it to be slightly longer than the loop interval that beat uses.
# This means beat wakes up, checks the schedule and extends the lock every
# CELERY_BEAT_MAX_LOOP_INTERVAL seconds. If it crashes or fails to wake up
# then 80 seconds after the lock was last extended it will be released and a new
# scheduler will acquire the lock and take over.
CELERY_REDBEAT_LOCK_TIMEOUT = os.getenv(
    "CELERY_REDBEAT_LOCK_TIMEOUT", CELERY_BEAT_MAX_LOOP_INTERVAL + 60
)

CELERY_RESULT_BACKEND = REDIS_URL
CELERY_RESULT_EXPIRES = int(
    # default 1 hour
    os.getenv("CELERY_RESULT_EXPIRES") or 3600
)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases
if "DATABASE_URL" in os.environ:
    DATABASES = {"default": dj_database_url.parse(os.getenv("DATABASE_URL"))}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DATABASE_NAME", "baserow"),
            "USER": os.getenv("DATABASE_USER", "baserow"),
            "PASSWORD": os.getenv("DATABASE_PASSWORD", "baserow"),
            "HOST": os.getenv("DATABASE_HOST", "db"),
            "PORT": os.getenv("DATABASE_PORT", "5432"),
        }
    }
    if "DATABASE_OPTIONS" in os.environ:
        DATABASES["default"]["OPTIONS"] = json.loads(
            os.getenv("DATABASE_OPTIONS", "{}")
        )

DATABASE_READ_REPLICAS = []

# Loop over all environment variables to extract read only replicas. Multiple nodes can
# be added providing `DATABASE_READ_{n}_URL`, or DATABASE_READ_{n}_NAME, where {n} is
# the key of the read-only instance.
for key, value in os.environ.items():
    if key.startswith("DATABASE_READ_REPLICA_") and key.endswith("_URL"):
        suffix = key[len("DATABASE_READ_REPLICA_") : -len("_URL")]
        db_key = f"read_{suffix}"
        DATABASES[db_key] = dj_database_url.parse(value)
        DATABASE_READ_REPLICAS.append(db_key)
    elif key.startswith("DATABASE_READ_") and key.endswith("_NAME"):
        suffix = key[len("DATABASE_READ_") : -len("_NAME")]
        db_key = f"read_{suffix}"

        DATABASES[db_key] = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv(f"DATABASE_READ_{suffix}_NAME"),
            "USER": os.getenv(f"DATABASE_READ_{suffix}_USER"),
            "PASSWORD": os.getenv(f"DATABASE_READ_{suffix}_PASSWORD"),
            "HOST": os.getenv(f"DATABASE_READ_{suffix}_HOST"),
            "PORT": os.getenv(f"DATABASE_READ_{suffix}_PORT"),
        }

        options = os.getenv(f"DATABASE_READ_{suffix}_OPTIONS")
        if options:
            DATABASES[db_key]["OPTIONS"] = json.loads(options)

        DATABASE_READ_REPLICAS.append(db_key)

# Default 0 = new connection per request; each runs a locale-setting query.
# Increase in WSGI to save those round-trips. In ASGI be careful: async tasks
# open their own connections and persistent ones can exhaust the pool.
BASEROW_CONN_MAX_AGE = int(os.getenv("BASEROW_CONN_MAX_AGE", 0))

# Apply the configured connection reuse timeout consistently to every database.
# Also enable connection health checks by default so Django verifies that a
# connection is still usable before each request/task, which prevents
# "connection already closed" errors when connections are dropped by the server,
# a load balancer, or a connection pooler.
for _db_key in DATABASES:
    DATABASES[_db_key]["CONN_MAX_AGE"] = BASEROW_CONN_MAX_AGE
    DATABASES[_db_key].setdefault("CONN_HEALTH_CHECKS", True)

DATABASE_ROUTERS = ["baserow.config.db_routers.ReadReplicaRouter"]


GENERATED_MODEL_CACHE_NAME = "generated-models"
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "baserow-default-cache",
        "VERSION": VERSION,
    },
    GENERATED_MODEL_CACHE_NAME: {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": f"baserow-{GENERATED_MODEL_CACHE_NAME}-cache",
        "VERSION": None,
    },
}

BUILDER_PUBLICLY_USED_PROPERTIES_CACHE_TTL_SECONDS = int(
    # Default TTL is 2 hours
    os.getenv("BASEROW_BUILDER_PUBLICLY_USED_PROPERTIES_CACHE_TTL_SECONDS")
    or 60 * 60 * 2
)
BUILDER_DISPATCH_ACTION_CACHE_TTL_SECONDS = int(
    # Default TTL is 5 minutes
    os.getenv("BASEROW_BUILDER_DISPATCH_ACTION_CACHE_TTL_SECONDS") or 300
)


CELERY_SINGLETON_BACKEND_CLASS = (
    "baserow.celery_singleton_backend.RedisBackendForSingleton"
)

# This flag enable automatic index creation for table views based on sortings.
AUTO_INDEX_VIEW_ENABLED = os.getenv("BASEROW_AUTO_INDEX_VIEW_ENABLED", "true") == "true"
AUTO_INDEX_LOCK_EXPIRY = os.getenv("BASEROW_AUTO_INDEX_LOCK_EXPIRY", 60 * 2)

# Should contain the database connection name of the database where the user tables
# are stored. This can be different than the default database because there are not
# going to be any relations between the application schema and the user schema.
USER_TABLE_DATABASE = "default"

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "baserow.core.user.password_validation.MaximumLengthValidator",
    },
]

# We need the `AllowAllUsersModelBackend` in order to respond with a proper error
# message when the user is not active. The only thing it does, is allowing non active
# users to authenticate, but the user still can't obtain or use a JWT token or database
# token because the user needs to be active to use that.
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.AllowAllUsersModelBackend"]

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/

LANGUAGE_CODE = "en"

# Must stay in sync with `locales` in web-frontend/config/locales.js: the account
# language endpoint validates against these codes (baserow.api.user.validators).
LANGUAGES = [
    ("en", "English"),
    ("pt-BR", "Portuguese (Brazil)"),
]

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Collation that the backend database should
# support in order to make front end and back end
# collations as close as possible to match sorting and
# other operations.
EXPECTED_COLLATION = "en-x-icu"

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/

STATIC_URL = "/static/"

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "baserow.api.user_sources.authentication.UserSourceJSONWebTokenAuthentication",
        "baserow.api.authentication.JSONWebTokenAuthentication",
    ),
    "DEFAULT_RENDERER_CLASSES": ("baserow.api.renderers.BaserowJSONRenderer",),
    "DEFAULT_SCHEMA_CLASS": "baserow.api.openapi.AutoSchema",
}

# Throttling / rate-limiting — see docs/installation/configuration.md
BASEROW_MAX_CONCURRENT_USER_REQUESTS = int(
    os.getenv("BASEROW_MAX_CONCURRENT_USER_REQUESTS", "") or -1
)
BASEROW_CONCURRENT_USER_REQUESTS_THROTTLE_TIMEOUT = int(
    os.getenv("BASEROW_CONCURRENT_USER_REQUESTS_THROTTLE_TIMEOUT", 180)
)
BASEROW_THROTTLE_BLACKLIST_TTL_SECONDS = int(
    os.getenv("BASEROW_THROTTLE_BLACKLIST_TTL_SECONDS", "") or -1
)
BASEROW_THROTTLE_IP_ENABLED = str_to_bool(os.getenv("BASEROW_THROTTLE_IP_ENABLED", ""))

if BASEROW_MAX_CONCURRENT_USER_REQUESTS > 0:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
        "baserow.throttling.handler.ConcurrentUserRequestsThrottle",
    ]

    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
        "concurrent_user_requests": BASEROW_MAX_CONCURRENT_USER_REQUESTS
    }

    if BASEROW_THROTTLE_BLACKLIST_TTL_SECONDS > 0:
        # Insert after SecurityMiddleware so 429s still get security/CORS headers.
        _security_idx = MIDDLEWARE.index(
            "django.middleware.security.SecurityMiddleware"
        )
        MIDDLEWARE.insert(
            _security_idx + 1,
            "baserow.throttling.middleware.ThrottleBlacklistMiddleware",
        )

    MIDDLEWARE += [
        "baserow.throttling.middleware.ConcurrentUserRequestsMiddleware",
    ]

BASEROW_CACHE_TTL_SECONDS = int(os.getenv("BASEROW_CACHE_TTL_SECONDS", 120))

PUBLIC_VIEW_AUTHORIZATION_HEADER = "Baserow-View-Authorization"

CORS_ORIGIN_ALLOW_ALL = True
CLIENT_SESSION_ID_HEADER = "ClientSessionId"
MAX_CLIENT_SESSION_ID_LENGTH = 256

CLIENT_UNDO_REDO_ACTION_GROUP_ID_HEADER = "ClientUndoRedoActionGroupId"
MAX_UNDOABLE_ACTIONS_PER_ACTION_GROUP = 20
WEBSOCKET_ID_HEADER = "WebsocketId"

USER_SOURCE_AUTHENTICATION_HEADER = "UserSourceAuthorization"

CORS_ALLOW_HEADERS = list(default_headers) + [
    WEBSOCKET_ID_HEADER,
    PUBLIC_VIEW_AUTHORIZATION_HEADER,
    CLIENT_SESSION_ID_HEADER,
    CLIENT_UNDO_REDO_ACTION_GROUP_ID_HEADER,
    USER_SOURCE_AUTHENTICATION_HEADER,
]

ACCESS_TOKEN_LIFETIME = timedelta(
    minutes=int(os.getenv("BASEROW_ACCESS_TOKEN_LIFETIME_MINUTES", 10))  # 10 minutes
)
REFRESH_TOKEN_LIFETIME = timedelta(
    hours=int(os.getenv("BASEROW_REFRESH_TOKEN_LIFETIME_HOURS", 24 * 7))  # 7 days
)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": ACCESS_TOKEN_LIFETIME,
    "REFRESH_TOKEN_LIFETIME": REFRESH_TOKEN_LIFETIME,
    "AUTH_HEADER_TYPES": ("JWT",),
    # It is recommended that you set BASEROW_JWT_SIGNING_KEY so it is independent
    # from the Django SECRET_KEY. This will make changing the signing key used for
    # tokens easier in the event that it is compromised.
    "SIGNING_KEY": os.getenv("BASEROW_JWT_SIGNING_KEY") or os.getenv("SECRET_KEY"),
    "USER_AUTHENTICATION_RULE": lambda user: user is not None,
}

# The product name shown in emails and the API docs. It reads the same variable
# as the web-frontend's runtime branding (docs/installation/branding.md), so one
# value renames both halves. An empty value counts as unset because Compose
# passes unset variables through as empty strings.
BRANDING_APP_NAME = os.getenv("BASEROW_BRANDING_APP_NAME") or "Saveroom"

SPECTACULAR_SETTINGS = {
    "TITLE": f"{BRANDING_APP_NAME} API spec",
    "DESCRIPTION": "For more information about our REST API, please visit "
    "[this page](https://github.com/carneirofc/baserow).\n\n"
    "For more information about our deprecation policy, please visit "
    "[this page](https://github.com/carneirofc/baserow).",
    "CONTACT": {"url": "https://github.com/carneirofc/baserow"},
    "LICENSE": {
        "name": "MIT",
        "url": "https://github.com/carneirofc/baserow/blob/develop/LICENSE",
    },
    "VERSION": "2.3.2",
    "SERVE_INCLUDE_SCHEMA": False,
    "TAGS": [
        {"name": "Settings"},
        {"name": "User"},
        {"name": "User files"},
        {"name": "Workspaces"},
        {"name": "Templates"},
        {"name": "Trash"},
        {"name": "Applications"},
        {"name": "Snapshots"},
        {"name": "Jobs"},
        {"name": "Integrations"},
        {"name": "User sources"},
        {"name": "Database tables"},
        {"name": "Database table fields"},
        {"name": "Database table views"},
        {"name": "Database table view filters"},
        {"name": "Database table view sortings"},
        {"name": "Database table view decorations"},
        {"name": "Database table view groupings"},
        {"name": "Database table view export"},
        {"name": "Database table grid view"},
        {"name": "Database table gallery view"},
        {"name": "Database table form view"},
        {"name": "Database table kanban view"},
        {"name": "Database table calendar view"},
        {"name": "Database table rows"},
        {"name": "Database table export"},
        {"name": "Database table webhooks"},
        {"name": "Database tokens"},
        {"name": "Builder pages"},
        {"name": "Builder elements"},
        {"name": "Builder domains"},
        {"name": "Builder public"},
        {"name": "Builder data sources"},
        {"name": "Builder workflow actions"},
        {"name": "Builder theme"},
        {"name": "Admin"},
    ],
    "ENUM_NAME_OVERRIDES": {
        "NumberDecimalPlacesEnum": [
            (0, "1"),
            (1, "1.0"),
            (2, "1.00"),
            (3, "1.000"),
            (4, "1.0000"),
            (5, "1.00000"),
        ],
        "ViewTypesEnum": [
            "grid",
            "gallery",
            "form",
            "kanban",
            "calendar",
        ],
        "FieldTypesEnum": [
            "text",
            "long_text",
            "url",
            "email",
            "number",
            "rating",
            "boolean",
            "date",
            "last_modified",
            "created_on",
            "link_row",
            "file",
            "single_select",
            "multiple_select",
            "phone_number",
            "formula",
            "count",
            "lookup",
            "url",
        ],
        "ViewFilterTypesEnum": [
            "equal",
            "not_equal",
            "filename_contains",
            "has_file_type",
            "files_lower_than",
            "contains",
            "contains_not",
            "length_is_lower_than",
            "higher_than",
            "lower_than",
            "date_equal",
            "date_before",
            "date_after",
            "date_not_equal",
            "date_equals_today",
            "date_equals_days_ago",
            "date_equals_week",
            "date_equals_month",
            "date_equals_day_of_month",
            "date_equals_year",
            "single_select_equal",
            "single_select_not_equal",
            "link_row_has",
            "link_row_has_not",
            "boolean",
            "empty",
            "not_empty",
            "multiple_select_has",
            "multiple_select_has_not",
        ],
        "EventTypesEnum": ["rows.created", "rows.updated", "rows.deleted"],
    },
}

BASEROW_FILE_UPLOAD_SIZE_LIMIT_MB = int(
    Decimal(os.getenv("BASEROW_FILE_UPLOAD_SIZE_LIMIT_MB", 1024 * 1024)) * 1024 * 1024
)  # ~1TB by default

# Django rejects any request body above this size. Since DRF 3.17.2 the JSON parser
# reads the body through `request.body`, so this also caps JSON payloads. Table
# imports send the parsed file as JSON, and the web-frontend accepts import files up
# to BASEROW_MAX_IMPORT_FILE_SIZE_MB (512 by default), so this must stay well above
# that once JSON overhead is added. Django's own 2.5MB default breaks imports.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    Decimal(os.getenv("BASEROW_MAX_REQUEST_BODY_SIZE_MB", 1024)) * 1024 * 1024
)

FILE_UPLOAD_ACTIVE_CONTENT_POLICY = os.getenv(
    "BASEROW_FILE_UPLOAD_ACTIVE_CONTENT_POLICY", "download"
).lower()
if FILE_UPLOAD_ACTIVE_CONTENT_POLICY not in ("download", "block"):
    raise ImproperlyConfigured(
        "BASEROW_FILE_UPLOAD_ACTIVE_CONTENT_POLICY must be set to "
        "'download' or 'block'."
    )

# Allows accessing and setting values on a dictionary like an object. Using this
# we can pass plugin authors and other functions a `settings` object which can modify
# the settings like they expect (settings.SETTING = 'test') etc.


class AttrDict(dict):
    def __getattr__(self, item):
        return super().__getitem__(item)

    def __setattr__(self, item, value):
        globals()[item] = value

    def __setitem__(self, key, value):
        globals()[key] = value


BASE_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

AWS_STORAGE_ENABLED = os.getenv("AWS_STORAGE_BUCKET_NAME", "") != ""
GOOGLE_STORAGE_ENABLED = os.getenv("GS_BUCKET_NAME", "") != ""
AZURE_STORAGE_ENABLED = os.getenv("AZURE_ACCOUNT_NAME", "") != ""

ALL_STORAGE_ENABLED_VARS = [
    AZURE_STORAGE_ENABLED,
    GOOGLE_STORAGE_ENABLED,
    AWS_STORAGE_ENABLED,
]
if sum(ALL_STORAGE_ENABLED_VARS) > 1:
    raise ImproperlyConfigured(
        "You have enabled more than one user file storage backend, please make sure "
        "you set only one of AWS_ACCESS_KEY_ID, GS_BUCKET_NAME and AZURE_ACCOUNT_NAME."
    )

if AWS_STORAGE_ENABLED:
    BASE_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_S3_FILE_OVERWRITE = False
    # This is needed to write the media file in a single call to `files_zip.writestr`
    # as described here: https://github.com/kobotoolbox/kobocat/issues/475
    AWS_S3_FILE_BUFFER_SIZE = BASEROW_FILE_UPLOAD_SIZE_LIMIT_MB
    set_settings_from_env_if_present(
        AttrDict(vars()),
        [
            "AWS_S3_SESSION_PROFILE",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_STORAGE_BUCKET_NAME",
            Setting(
                "AWS_S3_OBJECT_PARAMETERS",
                parser=json.loads,
                default={
                    "CacheControl": "max-age=86400",
                },
            ),
            Setting("AWS_DEFAULT_ACL", default="public-read"),
            Setting("AWS_QUERYSTRING_AUTH", parser=str_to_bool),
            Setting("AWS_S3_MAX_MEMORY_SIZE", parser=int),
            Setting("AWS_QUERYSTRING_EXPIRE", parser=int),
            "AWS_S3_URL_PROTOCOL",
            "AWS_S3_REGION_NAME",
            "AWS_S3_ENDPOINT_URL",
            "AWS_S3_CUSTOM_DOMAIN",
            "AWS_LOCATION",
            Setting("AWS_IS_GZIPPED", parser=str_to_bool),
            "GZIP_CONTENT_TYPES",
            Setting("AWS_S3_USE_SSL", parser=str_to_bool),
            Setting("AWS_S3_VERIFY", parser=str_to_bool),
            Setting(
                "AWS_SECRET_ACCESS_KEY_FILE_PATH",
                setting_name="AWS_SECRET_ACCESS_KEY",
                parser=read_file,
            ),
            "AWS_S3_ADDRESSING_STYLE",
            Setting("AWS_S3_PROXIES", parser=json.loads),
            "AWS_S3_SIGNATURE_VERSION",
            Setting("AWS_CLOUDFRONT_KEY", parser=lambda s: s.encode("ascii")),
            "AWS_CLOUDFRONT_KEY_ID",
        ],
    )


if GOOGLE_STORAGE_ENABLED:
    from google.oauth2 import service_account

    # See https://django-storages.readthedocs.io/en/latest/backends/gcloud.html for
    # details on what these env variables do

    BASE_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
    GS_FILE_OVERWRITE = False
    set_settings_from_env_if_present(
        AttrDict(vars()),
        [
            "GS_BUCKET_NAME",
            "GS_PROJECT_ID",
            Setting("GS_IS_GZIPPED", parser=str_to_bool),
            "GZIP_CONTENT_TYPES",
            Setting("GS_DEFAULT_ACL", default="publicRead"),
            Setting("GS_QUERYSTRING_AUTH", parser=str_to_bool),
            Setting("GS_MAX_MEMORY_SIZE", parser=int),
            Setting("GS_BLOB_CHUNK_SIZE", parser=int),
            Setting("GS_OBJECT_PARAMETERS", parser=json.loads),
            "GS_CUSTOM_ENDPOINT",
            "GS_LOCATION",
            Setting("GS_EXPIRATION", parser=int),
            Setting(
                "GS_CREDENTIALS_FILE_PATH",
                setting_name="GS_CREDENTIALS",
                parser=service_account.Credentials.from_service_account_file,
            ),
        ],
    )

if AZURE_STORAGE_ENABLED:
    BASE_FILE_STORAGE = "storages.backends.azure_storage.AzureStorage"
    AZURE_OVERWRITE_FILES = False
    set_settings_from_env_if_present(
        AttrDict(vars()),
        [
            "AZURE_ACCOUNT_NAME",
            "AZURE_ACCOUNT_KEY",
            Setting(
                "AZURE_ACCOUNT_KEY_FILE_PATH",
                setting_name="AZURE_ACCOUNT_KEY",
                parser=read_file,
            ),
            "AZURE_CONTAINER",
            Setting("AZURE_SSL", parser=str_to_bool),
            Setting("AZURE_UPLOAD_MAX_CONN", parser=int),
            Setting("AZURE_CONNECTION_TIMEOUT_SECS", parser=int),
            Setting("AZURE_URL_EXPIRATION_SECS", parser=int),
            "AZURE_LOCATION",
            "AZURE_ENDPOINT_SUFFIX",
            "AZURE_CUSTOM_DOMAIN",
            "AZURE_CONNECTION_STRING",
            "AZURE_TOKEN_CREDENTIAL",
            "AZURE_CACHE_CONTROL",
            Setting("AZURE_OBJECT_PARAMETERS", parser=json.loads),
            "AZURE_API_VERSION",
        ],
    )

STORAGES = {
    "default": {
        "BACKEND": BASE_FILE_STORAGE,
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

BASEROW_PUBLIC_URL = os.getenv("BASEROW_PUBLIC_URL", "")
if BASEROW_PUBLIC_URL:
    PUBLIC_BACKEND_URL = BASEROW_PUBLIC_URL
    PUBLIC_WEB_FRONTEND_URL = BASEROW_PUBLIC_URL
else:
    PUBLIC_BACKEND_URL = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")
    PUBLIC_WEB_FRONTEND_URL = os.getenv(
        "PUBLIC_WEB_FRONTEND_URL", "http://localhost:3000"
    )

BASEROW_EMBEDDED_SHARE_URL = os.getenv("BASEROW_EMBEDDED_SHARE_URL")
if not BASEROW_EMBEDDED_SHARE_URL:
    BASEROW_EMBEDDED_SHARE_URL = PUBLIC_WEB_FRONTEND_URL

FRONTEND_COOKIE_PREFIX = os.getenv("BASEROW_FRONTEND_COOKIE_PREFIX", "")

MEDIA_URL_PATH = "/media/"
MEDIA_URL = os.getenv("MEDIA_URL", urljoin(PUBLIC_BACKEND_URL, MEDIA_URL_PATH))

PRIVATE_BACKEND_URL = os.getenv("PRIVATE_BACKEND_URL", "http://backend:8000")
PUBLIC_BACKEND_HOSTNAME = urlparse(PUBLIC_BACKEND_URL).hostname
PUBLIC_WEB_FRONTEND_HOSTNAME = urlparse(PUBLIC_WEB_FRONTEND_URL).hostname
BASEROW_EMBEDDED_SHARE_HOSTNAME = urlparse(BASEROW_EMBEDDED_SHARE_URL).hostname
MEDIA_URL_HOSTNAME = urlparse(MEDIA_URL).hostname
PRIVATE_BACKEND_HOSTNAME = urlparse(PRIVATE_BACKEND_URL).hostname

if PUBLIC_BACKEND_HOSTNAME:
    ALLOWED_HOSTS.append(PUBLIC_BACKEND_HOSTNAME)

if MEDIA_URL_HOSTNAME:
    ALLOWED_HOSTS.append(MEDIA_URL_HOSTNAME)

if PRIVATE_BACKEND_HOSTNAME:
    ALLOWED_HOSTS.append(PRIVATE_BACKEND_HOSTNAME)

# Parse BASEROW_EXTRA_PUBLIC_URLS - comma-separated list of additional public URLs
# where Baserow will be accessible. It's the same as the `BASEROW_PUBLIC_URL`, the
# only difference is that the `BASEROW_PUBLIC_URL` is used in emails.
BASEROW_EXTRA_PUBLIC_URLS = os.getenv("BASEROW_EXTRA_PUBLIC_URLS", "")
EXTRA_PUBLIC_BACKEND_HOSTNAMES = []
EXTRA_PUBLIC_WEB_FRONTEND_HOSTNAMES = []

if BASEROW_EXTRA_PUBLIC_URLS:
    extra_urls = [
        url.strip() for url in BASEROW_EXTRA_PUBLIC_URLS.split(",") if url.strip()
    ]

    for url in extra_urls:
        # Validate URL format - must start with http:// or https://
        if not url.startswith(("http://", "https://")):
            print(
                f"WARNING: BASEROW_EXTRA_PUBLIC_URLS contains invalid URL '{url}'. "
                "URLs must start with http:// or https://. Skipping."
            )
            continue

        parsed_url = urlparse(url)
        hostname = parsed_url.hostname

        if not hostname:
            print(f"WARNING: URL '{url}' has no hostname. Skipping.")
            continue

        if hostname not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(hostname)
        if hostname not in EXTRA_PUBLIC_BACKEND_HOSTNAMES:
            EXTRA_PUBLIC_BACKEND_HOSTNAMES.append(hostname)
        if hostname not in EXTRA_PUBLIC_WEB_FRONTEND_HOSTNAMES:
            EXTRA_PUBLIC_WEB_FRONTEND_HOSTNAMES.append(hostname)

FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@localhost")
# Align Django's built-in senders with the Baserow configured sender so that any
# code relying on Django defaults (e.g. the `Send email` action using instance
# SMTP) uses the configured FROM_EMAIL instead of `webmaster@localhost`.
DEFAULT_FROM_EMAIL = FROM_EMAIL
SERVER_EMAIL = FROM_EMAIL
RESET_PASSWORD_TOKEN_MAX_AGE = 60 * 60 * 2  # 2 hours
CHANGE_EMAIL_TOKEN_MAX_AGE = 60 * 60 * 12  # 12 hours

ROW_PAGE_SIZE_LIMIT = int(os.getenv("BASEROW_ROW_PAGE_SIZE_LIMIT", 200))
BATCH_ROWS_SIZE_LIMIT = int(
    os.getenv("BATCH_ROWS_SIZE_LIMIT", 200)
)  # How many rows can be modified at once.

MAX_FIELD_TEXT_LENGTH = int(os.getenv("BASEROW_MAX_FIELD_TEXT_LENGTH") or 1_000_000)

# Per table, how many rows changed by a dependency cascade (formulas, lookups,
# link row display values in other tables) are broadcast as exact realtime row
# updates. Above the limit subscribers receive a whole-table refresh event
# instead. Zero disables realtime events for dependant rows entirely.
DEPENDANT_ROWS_REALTIME_UPDATE_LIMIT = int(
    os.getenv("BASEROW_DEPENDANT_ROWS_REALTIME_UPDATE_LIMIT", 200)
)

SEARCH_UPDATE_BATCH_SIZE = int(
    os.getenv("BASEROW_SEARCH_UPDATE_BATCH_SIZE", 2000)
)  # How many rows to process per batch in search index updates.

# Maximum count of records considered as a 'small table' during field rule operations.
FIELD_RULE_ROWS_LIMIT = int(os.getenv("FIELD_RULE_ROWS_LIMIT", BATCH_ROWS_SIZE_LIMIT))

# Maximum count of records returned by local baserow data source
INTEGRATION_LOCAL_BASEROW_PAGE_SIZE_LIMIT = int(
    os.getenv("BASEROW_INTEGRATION_LOCAL_BASEROW_PAGE_SIZE_LIMIT", 200)
)
INTEGRATION_LOCAL_BASEROW_BATCH_OPERATION_SIZE_LIMIT = int(
    os.getenv("BASEROW_INTEGRATION_LOCAL_BASEROW_BATCH_OPERATION_SIZE_LIMIT", 1000)
)
INTEGRATION_ALLOW_SMTP_SERVICE_TO_USE_INSTANCE_SETTINGS = str_to_bool(
    os.getenv("BASEROW_INTEGRATION_ALLOW_SMTP_SERVICE_TO_USE_INSTANCE_SETTINGS", "true")
)

AUTOMATION_HISTORY_PAGE_SIZE_LIMIT = int(
    os.getenv("BASEROW_AUTOMATION_HISTORY_PAGE_SIZE_LIMIT", 100)
)
_legacy_workflow_rate_limit_max_runs = os.getenv(
    "BASEROW_AUTOMATION_WORKFLOW_RATE_LIMIT_MAX_RUNS"
)
_legacy_workflow_rate_limit_window_seconds = os.getenv(
    "BASEROW_AUTOMATION_WORKFLOW_RATE_LIMIT_CACHE_EXPIRY_SECONDS"
)
_automation_workflow_rate_limits_env = os.getenv(
    "BASEROW_AUTOMATION_WORKFLOW_RATE_LIMITS"
)
_automation_workflow_error_limits_env = os.getenv(
    "BASEROW_AUTOMATION_WORKFLOW_ERROR_LIMITS"
)

if _automation_workflow_rate_limits_env is not None:
    _automation_workflow_rate_limit_values = [
        int(value.strip())
        for value in _automation_workflow_rate_limits_env.split(",")
        if value.strip()
    ]
elif (
    _legacy_workflow_rate_limit_max_runs is not None
    or _legacy_workflow_rate_limit_window_seconds is not None
):
    _automation_workflow_rate_limit_values = [
        int(_legacy_workflow_rate_limit_max_runs or 10),
        int(_legacy_workflow_rate_limit_window_seconds or 5),
    ]
else:
    _automation_workflow_rate_limit_values = [10, 5, 30, 60 * 5, 100, 60 * 60]

if len(_automation_workflow_rate_limit_values) % 2 != 0:
    raise ImproperlyConfigured(
        "BASEROW_AUTOMATION_WORKFLOW_RATE_LIMITS must contain an even number of "
        "comma-separated integers formatted as max_runs,window_seconds pairs."
    )

AUTOMATION_WORKFLOW_RATE_LIMITS = tuple(
    (
        _automation_workflow_rate_limit_values[index],
        _automation_workflow_rate_limit_values[index + 1],
    )
    for index in range(0, len(_automation_workflow_rate_limit_values), 2)
)
AUTOMATION_WORKFLOW_HISTORY_RATE_LIMIT_CACHE_EXPIRY_SECONDS = int(
    os.getenv(
        "BASEROW_AUTOMATION_WORKFLOW_HISTORY_RATE_LIMIT_CACHE_EXPIRY_SECONDS",
        _legacy_workflow_rate_limit_window_seconds or 5,
    )
)
if _automation_workflow_error_limits_env is not None:
    _automation_workflow_error_limit_values = [
        int(value.strip())
        for value in _automation_workflow_error_limits_env.split(",")
        if value.strip()
    ]
else:
    _automation_workflow_error_limit_values = [20, 300]

if len(_automation_workflow_error_limit_values) % 2 != 0:
    raise ImproperlyConfigured(
        "BASEROW_AUTOMATION_WORKFLOW_ERROR_LIMITS must contain an even number of "
        "comma-separated integers formatted as max_errors,window_seconds pairs."
    )

AUTOMATION_WORKFLOW_ERROR_LIMITS = tuple(
    (
        _automation_workflow_error_limit_values[index],
        _automation_workflow_error_limit_values[index + 1],
    )
    for index in range(0, len(_automation_workflow_error_limit_values), 2)
)
AUTOMATION_WORKFLOW_MAX_CONSECUTIVE_ERRORS = int(
    os.getenv("BASEROW_AUTOMATION_WORKFLOW_MAX_CONSECUTIVE_ERRORS", 5)
)
AUTOMATION_WORKFLOW_TIMEOUT_HOURS = int(
    os.getenv("BASEROW_AUTOMATION_WORKFLOW_TIMEOUT_HOURS", 24)
)
AUTOMATION_WORKFLOW_HISTORY_MAX_DAYS = int(
    os.getenv("BASEROW_AUTOMATION_WORKFLOW_HISTORY_MAX_DAYS", 30)
)
AUTOMATION_WORKFLOW_HISTORY_MAX_ENTRIES = int(
    os.getenv("BASEROW_AUTOMATION_WORKFLOW_HISTORY_MAX_ENTRIES", 200)
)
AUTOMATION_WORKFLOW_HISTORY_MIN_RETENTION_DAYS = int(
    os.getenv("BASEROW_AUTOMATION_WORKFLOW_HISTORY_MIN_RETENTION_DAYS", 2)
)
AUTOMATION_WORKFLOW_HISTORY_CLEANUP_INTERVAL_MINUTES = int(
    os.getenv("BASEROW_AUTOMATION_WORKFLOW_HISTORY_CLEANUP_INTERVAL_MINUTES", 60)
)

TRASH_PAGE_SIZE_LIMIT = 200  # How many trash entries can be requested at once.

# How many unique row values can be requested at once.
BASEROW_UNIQUE_ROW_VALUES_SIZE_LIMIT = int(
    os.getenv("BASEROW_UNIQUE_ROW_VALUES_SIZE_LIMIT", 100)
)

# The amount of rows that can be imported when creating a table or data sync.
INITIAL_TABLE_DATA_LIMIT = None
if "INITIAL_TABLE_DATA_LIMIT" in os.environ:
    INITIAL_TABLE_DATA_LIMIT = int(os.getenv("INITIAL_TABLE_DATA_LIMIT"))

BASEROW_INITIAL_CREATE_SYNC_TABLE_DATA_LIMIT = int(
    os.getenv("BASEROW_INITIAL_CREATE_SYNC_TABLE_DATA_LIMIT", 5000)
)

MEDIA_ROOT = os.getenv("MEDIA_ROOT", "/baserow/media")

# Indicates the directory where the user files and user thumbnails are stored.
USER_FILES_DIRECTORY = "user_files"
USER_THUMBNAILS_DIRECTORY = "thumbnails"

EXPORT_FILES_DIRECTORY = "export_files"
EXPORT_CLEANUP_INTERVAL_MINUTES = 5
# If you change this default please also update the default for the web-frontend
# found in web-frontend/modules/core/module.js, which tells the user how long an
# export stays downloadable.
EXPORT_FILE_EXPIRE_MINUTES = int(os.getenv("EXPORT_FILE_EXPIRE_MINUTES", 60))

# Exported files and backups are downloaded through the API, streamed straight out of
# the storage, so that a download works regardless of whether the storage is a shared
# volume or an object store the browser cannot reach. The link handed to the browser
# carries a signed token instead of a JWT, because a plain anchor cannot send an
# Authorization header. It is short lived: it is minted when the list is rendered and
# clicked seconds later, and an expired one is reported as such.
BASEROW_EXPORT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS = int(
    os.getenv("BASEROW_EXPORT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS", "") or 600
)
# How much is read from the storage per chunk while streaming a download. Django's
# FileResponse default of 4096 bytes turns a multi gigabyte backup into hundreds of
# thousands of chunks.
BASEROW_EXPORT_DOWNLOAD_BLOCK_SIZE = int(
    os.getenv("BASEROW_EXPORT_DOWNLOAD_BLOCK_SIZE", "") or 64 * 1024
)

IMPORT_FILES_DIRECTORY = "import_files"

# How often a worker writes a probe file into the export directory so the web process
# can confirm it is looking at the same storage. Without this an export produced by a
# worker on one volume and served by a web process on another finishes successfully
# and then cannot be downloaded, with nothing anywhere saying why.
BASEROW_SHARED_STORAGE_PROBE_INTERVAL_MINUTES = int(
    os.getenv("BASEROW_SHARED_STORAGE_PROBE_INTERVAL_MINUTES", "") or 5
)

# The interval in minutes that the mentions cleanup job should run. This job will
# remove mentions that are no longer used.
STALE_MENTIONS_CLEANUP_INTERVAL_MINUTES = int(
    os.getenv("BASEROW_STALE_MENTIONS_CLEANUP_INTERVAL_MINUTES", "") or 360
)

# Indicates how frequently the workspace storage should be updated. Once every X number
# of hours.
BASEROW_UPDATE_WORKSPACE_STORAGE_USAGE_HOURS = 24

ONE_AM_CRONTAB_STR = "0 1 * * *"
BASEROW_SEAT_USAGE_JOB_CRONTAB = get_crontab_from_env(
    "BASEROW_SEAT_USAGE_JOB_CRONTAB", default_crontab=ONE_AM_CRONTAB_STR
)

EMAIL_BACKEND = "djcelery_email.backends.CeleryEmailBackend"

if os.getenv("EMAIL_SMTP", ""):
    CELERY_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    # EMAIL_SMTP_USE_TLS OR EMAIL_SMTP_USE_TLS for backwards compatibility after
    # fixing #448.
    EMAIL_USE_TLS = bool(os.getenv("EMAIL_SMTP_USE_TLS", "")) or bool(
        os.getenv("EMAIL_SMPT_USE_TLS", "")
    )
    EMAIL_HOST = os.getenv("EMAIL_SMTP_HOST", "localhost")
    EMAIL_PORT = os.getenv("EMAIL_SMTP_PORT", "25")
    EMAIL_HOST_USER = os.getenv("EMAIL_SMTP_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_SMTP_PASSWORD", "")

    EMAIL_USE_SSL = bool(os.getenv("EMAIL_SMTP_USE_SSL", ""))
    if EMAIL_USE_SSL and EMAIL_USE_TLS:
        raise ImproperlyConfigured(
            "EMAIL_SMTP_USE_SSL and EMAIL_SMTP_USE_TLS are "
            "mutually exclusive and both cannot be set at once."
        )

    EMAIL_SSL_CERTFILE = os.getenv("EMAIL_SMTP_SSL_CERTFILE_PATH", None)
    EMAIL_SSL_KEYFILE = os.getenv("EMAIL_SMTP_SSL_KEYFILE_PATH", None)
else:
    CELERY_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Enable email notifications globally. If disabled, tasks will reset the
# email_scheduled field without sending any emails.
EMAIL_NOTIFICATIONS_ENABLED = str_to_bool(
    os.getenv("BASEROW_EMAIL_NOTIFICATIONS_ENABLED", "true")
)
# The maximum amount of email notifications that can be sent per task. This
# equals the amount of users that will receive an email, since all the
# notifications for a user are sent in one email. If you want to limit the
# number of emails sent per minute, look at MAX_EMAILS_PER_MINUTE.
EMAIL_NOTIFICATIONS_LIMIT_PER_TASK = {
    "instant": int(os.getenv("BASEROW_EMAIL_NOTIFICATIONS_LIMIT_INSTANT", 50)),
    "daily": int(os.getenv("BASEROW_EMAIL_NOTIFICATIONS_LIMIT_DAILY", 1000)),
    "weekly": int(os.getenv("BASEROW_EMAIL_NOTIFICATIONS_LIMIT_WEEKLY", 5000)),
}
# The crontab used to schedule the instant email notifications task.
EMAIL_NOTIFICATIONS_INSTANT_CRONTAB = get_crontab_from_env(
    "BASEROW_EMAIL_NOTIFICATIONS_INSTANT_CRONTAB", default_crontab="* * * * *"
)
# The hour of the day (between 0 and 23) when the daily and weekly email
# notifications task is scheduled, according to the user timezone. Every hour a
# task is scheduled and only the users in the correct timezone will receive an
# email.
EMAIL_NOTIFICATIONS_DAILY_HOUR_OF_DAY = int(
    os.getenv("BASEROW_EMAIL_NOTIFICATIONS_DAILY_HOUR_OF_DAY", 0)
)
# The day of the week when the weekly email notifications task is scheduled,
# according to the user timezone (0: Monday, ..., 6: Sunday).
EMAIL_NOTIFICATIONS_WEEKLY_DAY_OF_WEEK = int(
    os.getenv("BASEROW_EMAIL_NOTIFICATIONS_WEEKLY_DAY_OF_WEEK", 0)
)
# 0 seconds means that the task will not be retried if the limit of users being
# notified is reached. Provide a positive number to enable retries after this many
# seconds.
EMAIL_NOTIFICATIONS_AUTO_RETRY_IF_LIMIT_REACHED_AFTER = (
    int(os.getenv("BASEROW_EMAIL_NOTIFICATIONS_AUTO_RETRY_IF_LIMIT_REACHED_AFTER", 0))
    or None
)

# The maximum number of notifications that are going to be listed in a single email.
# All the additional notifications are going to be included in a single "and x more"
MAX_NOTIFICATIONS_LISTED_PER_EMAIL = int(
    os.getenv("BASEROW_MAX_NOTIFICATIONS_LISTED_PER_EMAIL", 10)
)

# Look into `CeleryEmailBackend` for more information about these settings.
CELERY_EMAIL_CHUNK_SIZE = int(os.getenv("CELERY_EMAIL_CHUNK_SIZE", 10))
# Use a multiple of CELERY_EMAIL_CHUNK_SIZE to have a sensible rate limit.
MAX_EMAILS_PER_MINUTE = int(os.getenv("BASEROW_MAX_EMAILS_PER_MINUTE", 50))
CELERY_EMAIL_TASK_CONFIG = {
    "rate_limit": f"{int(MAX_EMAILS_PER_MINUTE / CELERY_EMAIL_CHUNK_SIZE)}/m",
}

BASEROW_SEND_VERIFY_EMAIL_RATE_LIMIT = RateLimit.from_string(
    os.getenv("BASEROW_SEND_VERIFY_EMAIL_RATE_LIMIT", "5/h")
)

login_action_limit_from_env = os.getenv("BASEROW_LOGIN_ACTION_LOG_LIMIT")
BASEROW_LOGIN_ACTION_LOG_LIMIT = (
    RateLimit.from_string(login_action_limit_from_env)
    if login_action_limit_from_env
    else RateLimit(period_in_seconds=60 * 5, number_of_calls=1)
)

# Configurable thumbnails that are going to be generated when a user uploads an image
# file.
USER_THUMBNAILS = {"tiny": [None, 21], "small": [48, 48], "card_cover": [300, 160]}

# The directory that contains the all the templates in JSON format. When for example
# the `sync_templates` management command is called, then the templates in the
# database will be synced with these files.
APPLICATION_TEMPLATES_DIR = os.path.join(BASE_DIR, "../../../templates")
# The slugs of the templates that are highlighted by default in the templates select
# modal. This fork ships no built-in templates, so the list is empty.
DEFAULT_APPLICATION_TEMPLATES = []
BASEROW_SYNC_TEMPLATES_PATTERN = os.getenv("BASEROW_SYNC_TEMPLATES_PATTERN", None)

MAX_FIELD_LIMIT = int(os.getenv("BASEROW_MAX_FIELD_LIMIT", 600))


# set max events to be returned by every ICal feed. Empty value means no limit.
BASEROW_ICAL_VIEW_MAX_EVENTS = try_int(
    os.getenv("BASEROW_ICAL_VIEW_MAX_EVENTS", None), None
)


# If you change this default please also update the default for the web-frontend found
# in web-frontend/modules/core/module.js:55
HOURS_UNTIL_TRASH_PERMANENTLY_DELETED = int(
    os.getenv("HOURS_UNTIL_TRASH_PERMANENTLY_DELETED", 24 * 3)
)
OLD_TRASH_CLEANUP_CHECK_INTERVAL_MINUTES = 5

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# For now force the old os dependant behaviour of file uploads as users might be relying
# on it. See
# https://docs.djangoproject.com/en/3.2/releases/3.0/#new-default-value-for-the-file-upload-permissions-setting
FILE_UPLOAD_PERMISSIONS = None

MAX_FORMULA_STRING_LENGTH = 10000
FORMULA_RANGE_MAX_ITEMS = int(os.getenv("BASEROW_FORMULA_RANGE_MAX_ITEMS", 10000))
MAX_FIELD_REFERENCE_DEPTH = 1000
DONT_UPDATE_FORMULAS_AFTER_MIGRATION = bool(
    os.getenv("DONT_UPDATE_FORMULAS_AFTER_MIGRATION", "")
)
EVERY_TEN_MINUTES = "*/10 * * * *"
PERIODIC_FIELD_UPDATE_TIMEOUT_MINUTES = int(
    os.getenv("BASEROW_PERIODIC_FIELD_UPDATE_TIMEOUT_MINUTES", 9)
)
PERIODIC_FIELD_UPDATE_CRONTAB = get_crontab_from_env(
    "BASEROW_PERIODIC_FIELD_UPDATE_CRONTAB", default_crontab=EVERY_TEN_MINUTES
)
BASEROW_PERIODIC_FIELD_UPDATE_UNUSED_WORKSPACE_INTERVAL_MIN = int(
    os.getenv("BASEROW_PERIODIC_FIELD_UPDATE_UNUSED_WORKSPACE_INTERVAL_MIN", 60)
)
PERIODIC_FIELD_UPDATE_QUEUE_NAME = os.getenv(
    "BASEROW_PERIODIC_FIELD_UPDATE_QUEUE_NAME", "export"
)
# Number of tasks the periodic field update is split into. Defaults to 1 (a single
# task, like the original job); raise it to spread the work across more workers.
PERIODIC_FIELD_UPDATE_BATCH_COUNT = int(
    os.getenv("BASEROW_PERIODIC_FIELD_UPDATE_BATCH_COUNT") or 1
)

BASEROW_WEBHOOKS_MAX_CONSECUTIVE_TRIGGER_FAILURES = int(
    os.getenv("BASEROW_WEBHOOKS_MAX_CONSECUTIVE_TRIGGER_FAILURES", 8)
)
BASEROW_WEBHOOKS_MAX_RETRIES_PER_CALL = int(
    os.getenv("BASEROW_WEBHOOKS_MAX_RETRIES_PER_CALL", 8)
)
BASEROW_WEBHOOKS_MAX_PER_TABLE = int(os.getenv("BASEROW_WEBHOOKS_MAX_PER_TABLE", 20))
BASEROW_WEBHOOKS_MAX_CALL_LOG_ENTRIES = int(
    os.getenv("BASEROW_WEBHOOKS_MAX_CALL_LOG_ENTRIES", 10)
)
BASEROW_WEBHOOKS_REQUEST_TIMEOUT_SECONDS = int(
    os.getenv("BASEROW_WEBHOOKS_REQUEST_TIMEOUT_SECONDS", 5)
)
BASEROW_WEBHOOKS_ALLOW_PRIVATE_ADDRESS = bool(
    os.getenv("BASEROW_WEBHOOKS_ALLOW_PRIVATE_ADDRESS", False)
)
BASEROW_WEBHOOKS_IP_BLACKLIST = [
    ip_network(ip.strip())
    for ip in os.getenv("BASEROW_WEBHOOKS_IP_BLACKLIST", "").split(",")
    if ip.strip() != ""
]
BASEROW_WEBHOOKS_IP_WHITELIST = [
    ip_network(ip.strip())
    for ip in os.getenv("BASEROW_WEBHOOKS_IP_WHITELIST", "").split(",")
    if ip.strip() != ""
]
BASEROW_WEBHOOKS_URL_REGEX_BLACKLIST = [
    re.compile(url_regex.strip())
    for url_regex in os.getenv("BASEROW_WEBHOOKS_URL_REGEX_BLACKLIST", "").split(",")
    if url_regex.strip() != ""
]
BASEROW_WEBHOOKS_URL_CHECK_TIMEOUT_SECS = int(
    os.getenv("BASEROW_WEBHOOKS_URL_CHECK_TIMEOUT_SECS", "10")
)
BASEROW_MAX_WEBHOOK_CALLS_IN_QUEUE_PER_WEBHOOK = (
    int(os.getenv("BASEROW_MAX_WEBHOOK_CALLS_IN_QUEUE_PER_WEBHOOK", "0")) or None
)
BASEROW_WEBHOOKS_BATCH_LIMIT = int(os.getenv("BASEROW_WEBHOOKS_BATCH_LIMIT", 5))
BASEROW_WEBHOOK_ROWS_ENTER_VIEW_BATCH_SIZE = int(
    os.getenv("BASEROW_WEBHOOK_ROWS_ENTER_VIEW_BATCH_SIZE", BATCH_ROWS_SIZE_LIMIT)
)

OAUTH_BACKEND_URL = os.getenv("BASEROW_OAUTH_BACKEND_URL") or PUBLIC_BACKEND_URL

INTEGRATIONS_ALLOW_PRIVATE_ADDRESS = bool(
    os.getenv("BASEROW_INTEGRATIONS_ALLOW_PRIVATE_ADDRESS", False)
)
BASEROW_DATA_SYNC_ALLOW_PRIVATE_ADDRESS = str_to_bool(
    os.getenv("BASEROW_DATA_SYNC_ALLOW_PRIVATE_ADDRESS") or "true"
)
INTEGRATIONS_PERIODIC_TASK_CRONTAB = crontab(minute="*")
# The minimum amount of minutes the periodic task's "minute" interval
# supports. Self-hosters can run every minute, if they choose to.
INTEGRATIONS_PERIODIC_MINUTE_MIN = int(
    os.getenv("BASEROW_INTEGRATIONS_PERIODIC_MINUTE_MIN") or 1
)

# How often the periodic task looks for backup schedules that became due. Every
# minute by default so a schedule fires close to the moment its cron expression says.
BASEROW_BACKUP_SCHEDULE_TICK_CRONTAB = get_crontab_from_env(
    "BASEROW_BACKUP_SCHEDULE_TICK_CRONTAB", default_crontab="* * * * *"
)

# Datalake (Parquet) table exports. The tick is how often due schedules are looked
# for; rows are read in chunks and split over part files of a bounded row count.
BASEROW_TABLE_EXPORT_SCHEDULE_TICK_CRONTAB = get_crontab_from_env(
    "BASEROW_TABLE_EXPORT_SCHEDULE_TICK_CRONTAB", default_crontab="* * * * *"
)
BASEROW_DATA_EXPORT_CHUNK_SIZE = int(
    os.getenv("BASEROW_DATA_EXPORT_CHUNK_SIZE", "5000")
)
BASEROW_DATA_EXPORT_MAX_ROWS_PER_FILE = int(
    os.getenv("BASEROW_DATA_EXPORT_MAX_ROWS_PER_FILE", "1000000")
)
# How far an incremental export reaches back before the previous snapshot, to catch
# rows committed with an older `updated_on` while that export was running.
BASEROW_DATA_EXPORT_WATERMARK_OVERLAP_SECONDS = int(
    os.getenv("BASEROW_DATA_EXPORT_WATERMARK_OVERLAP_SECONDS", "300")
)
# Where part files are written before they are uploaded. Empty uses the system default.
BASEROW_DATA_EXPORT_TMP_DIR = os.getenv("BASEROW_DATA_EXPORT_TMP_DIR", "") or None
BASEROW_DATA_EXPORT_SOFT_TIME_LIMIT = int(
    os.getenv("BASEROW_DATA_EXPORT_SOFT_TIME_LIMIT", str(6 * 60 * 60))
)

# The maximum amount of rows the `/api/contents/` endpoints return in one synchronous
# response. Larger requests are refused with ERROR_CONTENTS_TOO_LARGE and should use
# `/api/backups/` instead. Set to 0 to disable the limit.
BASEROW_CONTENTS_API_MAX_ROWS = int(
    os.getenv("BASEROW_CONTENTS_API_MAX_ROWS", "100000")
)

TOTP_ISSUER_NAME = os.getenv("BASEROW_TOTP_ISSUER_NAME") or BRANDING_APP_NAME

# ======== WARNING ========
# Please read and understand everything at:
# https://docs.djangoproject.com/en/3.2/ref/settings/#secure-proxy-ssl-header
# before enabling this setting otherwise you can compromise your site’s security.
# This setting will ensure the "next" urls provided by the various paginated API
# endpoints will be returned with https when appropriate.
# If using gunicorn also behind the proxy you might also need to set
# --forwarded-allow-ips='*'. See the following link for more information:
# https://stackoverflow.com/questions/62337379/how-to-append-nginx-ip-to-x-forwarded
# -for-in-kubernetes-nginx-ingress-controller

if bool(os.getenv("BASEROW_ENABLE_SECURE_PROXY_SSL_HEADER", False)):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DISABLE_ANONYMOUS_PUBLIC_VIEW_WS_CONNECTIONS = bool(
    os.getenv("DISABLE_ANONYMOUS_PUBLIC_VIEW_WS_CONNECTIONS", "")
)

PRESENCE_VISIBLE_USERS = int(os.getenv("BASEROW_PRESENCE_VISIBLE_USERS") or 3)

BASEROW_BACKEND_LOG_LEVEL = os.getenv("BASEROW_BACKEND_LOG_LEVEL", "INFO")
BASEROW_BACKEND_DATABASE_LOG_LEVEL = os.getenv(
    "BASEROW_BACKEND_DATABASE_LOG_LEVEL", "ERROR"
)

BASEROW_JOB_EXPIRATION_TIME_LIMIT = int(
    os.getenv("BASEROW_JOB_EXPIRATION_TIME_LIMIT", 30 * 24 * 60)  # 30 days
)
BASEROW_JOB_SOFT_TIME_LIMIT = int(
    os.getenv("BASEROW_JOB_SOFT_TIME_LIMIT", 60 * 30)  # 30 minutes
)
BASEROW_JOB_CLEANUP_INTERVAL_MINUTES = int(
    os.getenv("BASEROW_JOB_CLEANUP_INTERVAL_MINUTES", 5)  # 5 minutes
)
BASEROW_ROW_HISTORY_CLEANUP_INTERVAL_MINUTES = int(
    os.getenv("BASEROW_ROW_HISTORY_CLEANUP_INTERVAL_MINUTES", 30)  # 30 minutes
)
# Mirrored in web-frontend/modules/core/module.js so the row history panel can say
# how far back it reaches. Keep both defaults in sync.
BASEROW_ROW_HISTORY_RETENTION_DAYS = int(
    os.getenv("BASEROW_ROW_HISTORY_RETENTION_DAYS", 180)
)
BASEROW_MAX_ROW_REPORT_ERROR_COUNT = int(
    os.getenv("BASEROW_MAX_ROW_REPORT_ERROR_COUNT", 30)
)
BASEROW_MAX_SNAPSHOTS_PER_GROUP = int(os.getenv("BASEROW_MAX_SNAPSHOTS_PER_GROUP", 50))
# Mirrored in web-frontend/modules/core/module.js so the snapshot list can show how
# long each snapshot has left. Keep both defaults in sync.
BASEROW_SNAPSHOT_EXPIRATION_TIME_DAYS = int(
    os.getenv("BASEROW_SNAPSHOT_EXPIRATION_TIME_DAYS", 360)  # 360 days
)
BASEROW_USER_LOG_ENTRY_CLEANUP_INTERVAL_MINUTES = int(
    os.getenv("BASEROW_USER_LOG_ENTRY_CLEANUP_INTERVAL_MINUTES", 60)  # 60 minutes
)
# 61 days to accommodate timezone changes in admin dashboard. Mirrored in
# web-frontend/modules/core/module.js so the audit log can state its own window.
# Keep both defaults in sync.
BASEROW_USER_LOG_ENTRY_RETENTION_DAYS = int(
    os.getenv("BASEROW_USER_LOG_ENTRY_RETENTION_DAYS", 61)
)
BASEROW_IMPORT_EXPORT_RESOURCE_CLEANUP_INTERVAL_MINUTES = int(
    os.getenv("BASEROW_IMPORT_EXPORT_RESOURCE_CLEANUP_INTERVAL_MINUTES", 5)
)
BASEROW_IMPORT_EXPORT_RESOURCE_REMOVAL_AFTER_DAYS = int(
    os.getenv("BASEROW_IMPORT_EXPORT_RESOURCE_REMOVAL_AFTER_DAYS", 5)
)

# The maximum number of rows that will be exported when exporting a table.
# If `0` then all rows will be exported.
BASEROW_IMPORT_EXPORT_TABLE_ROWS_COUNT_LIMIT = int(
    os.getenv("BASEROW_IMPORT_EXPORT_TABLE_ROWS_COUNT_LIMIT", 0)
)

PERMISSION_MANAGERS = [
    # Must stay first: an application type disabled through the instance settings is
    # denied before any manager can allow the operation for another reason, such as the
    # workspace being a template or the builder application being published publicly.
    "application_type_enabled",
    "core",
    "setting_operation",
    "staff",
    "staff_bypass",
    "allow_if_template",
    "allow_public_builder",
    "element_visibility",
    "member",
    # In-app database/table access levels given to members and teams.
    "database_access",
    "token",
    "write_field_values",
    "basic",
    "automation_workflow",
    "automation_node",
]


OLD_ACTION_CLEANUP_INTERVAL_MINUTES = os.getenv(
    "OLD_ACTION_CLEANUP_INTERVAL_MINUTES", 5
)
MINUTES_UNTIL_ACTION_CLEANED_UP = os.getenv("MINUTES_UNTIL_ACTION_CLEANED_UP", "120")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "%(levelname)s %(asctime)s %(name)s.%(funcName)s:%(lineno)s- %("
            "message)s "
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "loggers": {
        "django.db.backends": {
            "handlers": ["console"],
            "level": BASEROW_BACKEND_DATABASE_LOG_LEVEL,
            "propagate": True,
        },
        # Default to ERROR to suppress 429 spam under heavy throttling.
        "django.request": {
            "handlers": ["console"],
            "level": os.getenv("BASEROW_DJANGO_REQUEST_LOG_LEVEL", "ERROR"),
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": BASEROW_BACKEND_LOG_LEVEL,
    },
}


# Now incorrectly named old variable, previously we would run `sync_templates` prior
# to starting the gunicorn server in Docker. This variable would prevent that from
# happening. Now we sync_templates in an async job triggered after migration.
# This variable if not true will now stop the async job from being triggered.
SYNC_TEMPLATES_ON_STARTUP = os.getenv("SYNC_TEMPLATES_ON_STARTUP", "true") == "true"
BASEROW_TRIGGER_SYNC_TEMPLATES_AFTER_MIGRATION = os.getenv(
    "BASEROW_TRIGGER_SYNC_TEMPLATES_AFTER_MIGRATION", None
)

if BASEROW_TRIGGER_SYNC_TEMPLATES_AFTER_MIGRATION is None:
    # If the new correctly named environment variable is not set, default to using
    # the old now incorrectly named SYNC_TEMPLATES_ON_STARTUP.
    BASEROW_TRIGGER_SYNC_TEMPLATES_AFTER_MIGRATION = SYNC_TEMPLATES_ON_STARTUP
else:
    # The new correctly named environment variable is set, so use that instead of
    # the old.
    BASEROW_TRIGGER_SYNC_TEMPLATES_AFTER_MIGRATION = (
        BASEROW_TRIGGER_SYNC_TEMPLATES_AFTER_MIGRATION == "true"
    )

BASEROW_SYNC_TEMPLATES_TIME_LIMIT = int(
    os.getenv("BASEROW_SYNC_TEMPLATES_TIME_LIMIT", 60 * 30)
)

APPEND_SLASH = False

BASEROW_DISABLE_MODEL_CACHE = bool(os.getenv("BASEROW_DISABLE_MODEL_CACHE", ""))
BASEROW_NOWAIT_FOR_LOCKS = not bool(
    os.getenv("BASEROW_WAIT_INSTEAD_OF_409_CONFLICT_ERROR", False)
)

# How often the user source user count is recalculated. Used to spread the counting
# of registered user source types across that interval instead of doing it all at once.
BASEROW_USER_SOURCE_COUNTING_TASK_INTERVAL_MINUTES = int(
    os.getenv("BASEROW_USER_SOURCE_COUNTING_TASK_INTERVAL_MINUTES", "") or 15
)

# Set this to True to enable users to login with auth providers different than the one
# they were originally created with. Read by `AuthProviderType.get_user_and_sign_in`,
# which third party authentication plugins inherit.
BASEROW_ALLOW_MULTIPLE_SSO_PROVIDERS_FOR_SAME_ACCOUNT = str_to_bool(
    os.getenv("BASEROW_ALLOW_MULTIPLE_SSO_PROVIDERS_FOR_SAME_ACCOUNT", "")
)

# Env-configured OpenID Connect providers. Declared as a JSON list; parsed and
# structurally validated here so an invalid configuration fails fast at startup.
from baserow.core.sso.oidc.config import (  # noqa: E402
    parse_oidc_providers_env,
)

BASEROW_OIDC_PROVIDERS = parse_oidc_providers_env(
    os.getenv("BASEROW_OIDC_PROVIDERS", "")
)

# When enabled, the instance is OIDC-only for normal users: self-service password
# signup is disabled and password login is refused for non-staff accounts. A staff /
# superuser (break-glass admin) can still log in with a password.
BASEROW_OIDC_ONLY = str_to_bool(os.getenv("BASEROW_OIDC_ONLY", ""))

# Env-declared external data destinations (S3, Azure Blob Storage or a mounted
# filesystem) that backups and datalake table exports are written to. Declared as a
# JSON list so credentials never live in the database; validated here to fail fast.
from baserow.core.data_destinations.config import (  # noqa: E402
    parse_data_destinations_env,
)

BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
    os.getenv("BASEROW_DATA_DESTINATIONS", "")
)

MIGRATION_LOCK_ID = os.getenv("BASEROW_MIGRATION_LOCK_ID", 123456)
DEFAULT_SEARCH_MODE = os.getenv("BASEROW_DEFAULT_SEARCH_MODE", "compat")


# Search specific configuration settings.
CELERY_SEARCH_UPDATE_HARD_TIME_LIMIT = int(
    os.getenv("BASEROW_CELERY_SEARCH_UPDATE_HARD_TIME_LIMIT", 60 * 60)  # 1 hour
)
# By default, Baserow will use Postgres full-text as its
# search backend. If the product is installed on a system
# with limited disk space, and less accurate results / degraded
# search performance is acceptable, then switch this setting off.
PG_FULLTEXT_SEARCH_ENABLED = str_to_bool(
    (os.getenv("BASEROW_USE_PG_FULLTEXT_SEARCH", "true"))
)
PG_FULLTEXT_SEARCH_CONFIG = os.getenv("BASEROW_PG_SEARCH_CONFIG", "simple")
PG_FULLTEXT_SEARCH_UPDATE_DATA_THROTTLE_SECONDS = float(
    os.getenv("BASEROW_PG_FULLTEXT_SEARCH_UPDATE_DATA_THROTTLE_SECONDS", 2)  # seconds
)

BASEROW_BUILDER_DOMAINS = os.getenv("BASEROW_BUILDER_DOMAINS", None)
BASEROW_BUILDER_DOMAINS = (
    BASEROW_BUILDER_DOMAINS.split(",") if BASEROW_BUILDER_DOMAINS is not None else []
)

# Indicates whether we are running the tests or not. Set to True in the test.py settings
# file used by pytest.ini
TESTS = False


for plugin in [*BASEROW_BUILT_IN_PLUGINS, *BASEROW_BACKEND_PLUGIN_NAMES]:
    try:
        mod = importlib.import_module(plugin + ".config.settings.settings")
        # The plugin should have a setup function which accepts a 'settings' object.
        # This settings object is an AttrDict shadowing our local variables so the
        # plugin can access the Django settings and modify them prior to startup.
        result = mod.setup(AttrDict(vars()))
    except ImportError as e:
        print("Could not import %s", plugin)
        print(e)


# Libraries that should be lazy-loaded (imported inside functions/methods) to reduce
# memory footprint at startup. If any of these are found in sys.modules during startup,
# a warning will be shown suggesting to either lazy-load them or remove them from this
# list if they're legitimately needed at startup.
BASEROW_LAZY_LOADED_LIBRARIES = [
    "jira2markdown",
    "saml2",
    "openpyxl",
    "numpy",
]


BASEROW_TWO_WAY_SYNC_MAX_CONSECUTIVE_FAILURES = int(
    os.getenv("BASEROW_TWO_WAY_SYNC_MAX_CONSECUTIVE_FAILURES", "") or 8
)
BASEROW_TWO_WAY_SYNC_MAX_RETRIES = int(
    os.getenv("BASEROW_TWO_WAY_SYNC_MAX_RETRIES", "") or 3
)

BASEROW_PREVENT_POSTGRESQL_DATA_SYNC_CONNECTION_TO_DATABASE = str_to_bool(
    os.getenv("BASEROW_PREVENT_POSTGRESQL_DATA_SYNC_CONNECTION_TO_DATABASE", "true")
)
BASEROW_POSTGRESQL_DATA_SYNC_BLACKLIST = os.getenv(
    "BASEROW_POSTGRESQL_DATA_SYNC_BLACKLIST", ""
)
BASEROW_POSTGRESQL_DATA_SYNC_BLACKLIST = (
    BASEROW_POSTGRESQL_DATA_SYNC_BLACKLIST.split(",")
    if BASEROW_POSTGRESQL_DATA_SYNC_BLACKLIST
    else []
)
BASEROW_POSTGRESQL_DATA_SYNC_STATEMENT_TIMEOUT = int(
    os.getenv("BASEROW_POSTGRESQL_DATA_SYNC_STATEMENT_TIMEOUT", "") or 180
)

# Default compression level for creating zip files. This setting balances the need to
# save resources when compressing media files with the need to save space when
# compressing text files.
BASEROW_DEFAULT_ZIP_COMPRESS_LEVEL = 5

BASEROW_MAX_HEALTHY_CELERY_QUEUE_SIZE = int(
    os.getenv("BASEROW_MAX_HEALTHY_CELERY_QUEUE_SIZE", "") or 10
)

BASEROW_USE_LOCAL_CACHE = str_to_bool(os.getenv("BASEROW_USE_LOCAL_CACHE", "true"))

# -- CACHALOT SETTINGS --

CACHALOT_TIMEOUT = int(os.getenv("BASEROW_CACHALOT_TIMEOUT", 60 * 60 * 24 * 7))
BASEROW_CACHALOT_ONLY_CACHABLE_TABLES = os.getenv(
    "BASEROW_CACHALOT_ONLY_CACHABLE_TABLES", None
)
BASEROW_CACHALOT_MODE = os.getenv("BASEROW_CACHALOT_MODE", "default")
if BASEROW_CACHALOT_MODE == "full":
    CACHALOT_ONLY_CACHABLE_TABLES = []

elif BASEROW_CACHALOT_ONLY_CACHABLE_TABLES:
    # Please avoid to add tables with more than 50 modifications per minute to this
    # list, as described here:
    # https://django-cachalot.readthedocs.io/en/latest/limits.html
    CACHALOT_ONLY_CACHABLE_TABLES = BASEROW_CACHALOT_ONLY_CACHABLE_TABLES.split(",")
else:
    CACHALOT_ONLY_CACHABLE_TABLES = [
        "auth_user",
        "django_content_type",
        "core_settings",
        "core_userprofile",
        "core_application",
        "core_operation",
        "core_template",
        "core_trashentry",
        "core_workspace",
        "core_workspaceuser",
        "core_authprovidermodel",
        "core_passwordauthprovidermodel",
        "database_database",
        "database_table",
        "database_field",
        "database_fieldependency",
        "database_linkrowfield",
        "database_selectoption",
    ]

# This list will have priority over CACHALOT_ONLY_CACHABLE_TABLES.
BASEROW_CACHALOT_UNCACHABLE_TABLES = os.getenv(
    "BASEROW_CACHALOT_UNCACHABLE_TABLES", None
)

if BASEROW_CACHALOT_UNCACHABLE_TABLES:
    CACHALOT_UNCACHABLE_TABLES = list(
        filter(bool, BASEROW_CACHALOT_UNCACHABLE_TABLES.split(","))
    )

CACHALOT_ENABLED = str_to_bool(os.getenv("BASEROW_CACHALOT_ENABLED", ""))
CACHALOT_CACHE = "cachalot"
CACHALOT_UNCACHABLE_TABLES = [
    "django_migrations",
    "core_action",
    "database_token",
]


def install_cachalot():
    from baserow.cachalot_patch import patch_cachalot_for_baserow

    global INSTALLED_APPS

    INSTALLED_APPS.append("cachalot")

    patch_cachalot_for_baserow()


if CACHALOT_ENABLED:
    install_cachalot()

    CACHES[CACHALOT_CACHE] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": f"baserow-{CACHALOT_CACHE}-cache",
        "VERSION": VERSION,
    }
# -- END CACHALOT SETTINGS --


BASEROW_DEADLOCK_MAX_RETRIES = max(
    try_int(os.getenv("BASEROW_DEADLOCK_MAX_RETRIES"), 1),
    1,
)
BASEROW_DEADLOCK_INITIAL_BACKOFF = max(
    try_float(os.getenv("BASEROW_DEADLOCK_INITIAL_BACKOFF"), 0.2),
    0.1,
)

# Set to "all" to enable captcha everywhere, or a comma-separated list of contexts
# (currently only "signup") to enable only in specific places.
BASEROW_ENABLE_CAPTCHA = os.getenv("BASEROW_ENABLE_CAPTCHA", "")
BASEROW_CAPTCHA_PROVIDER = os.getenv("BASEROW_CAPTCHA_PROVIDER", "cloudflare_turnstile")
BASEROW_CLOUDFLARE_TURNSTILE_SITE_KEY = os.getenv(
    "BASEROW_CLOUDFLARE_TURNSTILE_SITE_KEY", ""
)
BASEROW_CLOUDFLARE_TURNSTILE_SECRET_KEY = os.getenv(
    "BASEROW_CLOUDFLARE_TURNSTILE_SECRET_KEY", ""
)

BASEROW_REALTIME_REPLAY_MAX_EVENTS = int(
    os.getenv("BASEROW_REALTIME_REPLAY_MAX_EVENTS", 200)
)

REALTIME_REPLAY_RETENTION_HOURS = int(
    os.getenv("BASEROW_REALTIME_REPLAY_RETENTION_HOURS", 24)
)
if REALTIME_REPLAY_RETENTION_HOURS <= 0:
    raise ImproperlyConfigured(
        "BASEROW_REALTIME_REPLAY_RETENTION_HOURS must be a positive integer."
    )
