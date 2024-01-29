"""
Django settings for EvaP project.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.0/ref/settings/
"""

import logging
import os
import sys
from typing import Any

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage

BASE_DIR = os.path.dirname(os.path.realpath(__file__))


### Debugging

DEBUG = True

# Very helpful but eats a lot of performance on sql-heavy pages.
# Works only with DEBUG = True and Django's development server (so no apache).
ENABLE_DEBUG_TOOLBAR = False

### EvaP logic

LOGIN_KEY_VALIDITY = 210  # days, so roughly 7 months

VOTER_COUNT_NEEDED_FOR_PUBLISHING_RATING_RESULTS = 2
VOTER_PERCENTAGE_NEEDED_FOR_PUBLISHING_AVERAGE_GRADE = 0.2
SMALL_COURSE_SIZE = 5  # up to which number of participants the evaluation gets additional warnings about anonymity

# a warning is shown next to results where less than RESULTS_WARNING_COUNT answers were given
# or the number of answers is less than RESULTS_WARNING_PERCENTAGE times the median number of answers (for this question in this evaluation)
RESULTS_WARNING_COUNT = 4
RESULTS_WARNING_PERCENTAGE = 0.5

## percentages for calculating an evaluation's total average grade
# grade questions are weighted this much for each contributor's average grade
CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT = 4
# non-grade questions are weighted this much for each contributor's average grade
CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT = 6
# the average contribution grade is weighted this much for the evaluation's average grade
CONTRIBUTIONS_WEIGHT = 1
# the average grade of all general grade questions is weighted this much for the evaluation's average grade
GENERAL_GRADE_QUESTIONS_WEIGHT = 1
# the average grade of all general non-grade questions is weighted this much for the evaluation's average grade
GENERAL_NON_GRADE_QUESTIONS_WEIGHT = 1

# number of reward points a student should have for a semester after evaluating the given fraction of evaluations.
REWARD_POINTS = [
    (1 / 3, 1),
    (2 / 3, 2),
    (3 / 3, 3),
]

# days before end date to send reminder
REMIND_X_DAYS_AHEAD_OF_END_DATE = [2, 0]

# days of the week on which managers are reminded to handle urgent text answer reviews
# where Monday is 0 and Sunday is 6
TEXTANSWER_REVIEW_REMINDER_WEEKDAYS = [3]

# email domains for the internal users of the hosting institution used to
# figure out who is an internal user
INSTITUTION_EMAIL_DOMAINS = ["institution.example.com", "student.institution.example.com"]

# List of tuples defining email domains that should be replaced on saving UserProfiles.
# Emails ending on the first value will have this part replaced by the second value.
# e.g.: [("institution.example.com", "institution.com")]
INSTITUTION_EMAIL_REPLACEMENTS: list[tuple[str, str]] = []

# the importer accepts only these two strings in the 'graded' column
IMPORTER_GRADED_YES = "yes"
IMPORTER_GRADED_NO = "no"

# the importer will warn if any participant has more enrollments than this number
IMPORTER_MAX_ENROLLMENTS = 7

# Cutoff value passed to difflib.get_close_matches() to find typos in course names. Lower values are slower.
IMPORTER_COURSE_NAME_SIMILARITY_WARNING_THRESHOLD = 0.9

# the default descriptions for grade documents
DEFAULT_FINAL_GRADES_DESCRIPTION_EN = "Final grades"
DEFAULT_MIDTERM_GRADES_DESCRIPTION_EN = "Midterm grades"
DEFAULT_FINAL_GRADES_DESCRIPTION_DE = "Endnoten"
DEFAULT_MIDTERM_GRADES_DESCRIPTION_DE = "Zwischennoten"

# Specify an offset that will be added to the evaluation end date (e.g. 3: If the end date is 01.01., the evaluation will end at 02.01. 03:00.).
EVALUATION_END_OFFSET_HOURS = 3

# Amount of hours in which participant will be warned
EVALUATION_END_WARNING_PERIOD = 5


### Installation specific settings

# People who get emails on errors.
ADMINS: list[tuple[str, str]] = [
    # ('Your Name', 'your_email@example.com'),
]

# The page URL that is used in email templates.
PAGE_URL = "localhost:8000"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "evap",
        "USER": "postgres",
        "PASSWORD": "",
        "HOST": "",  # Set to empty string for localhost.
        "PORT": "",  # Set to empty string for default.
        "CONN_MAX_AGE": 600,
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/0",
    },
    "results": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "TIMEOUT": None,  # is always invalidated manually
    },
    "sessions": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/2",
    },
}


class ManifestStaticFilesStorageWithJsReplacement(ManifestStaticFilesStorage):
    support_js_module_import_aggregation = True


STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "evap.settings.ManifestStaticFilesStorageWithJsReplacement",
    },
}

CONTACT_EMAIL = "webmaster@localhost"
ALLOW_ANONYMOUS_FEEDBACK_MESSAGES = True

# Config for mail system
DEFAULT_FROM_EMAIL = "webmaster@localhost"
REPLY_TO_EMAIL = DEFAULT_FROM_EMAIL
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)s: %(message)s",
        },
    },
    "handlers": {
        "file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR + "/logs/evap.log",
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 5,
            "formatter": "default",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file", "mail_admins"],
            "level": "INFO",
            "propagate": True,
        },
        "evap": {
            "handlers": ["console", "file", "mail_admins"],
            "level": "DEBUG",
            "propagate": True,
        },
        "mozilla_django_oidc": {
            "handlers": ["console", "file", "mail_admins"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}


### Application definition

AUTH_USER_MODEL = "evaluation.UserProfile"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    "evap.evaluation",
    "evap.staff",
    "evap.results",
    "evap.student",
    "evap.contributor",
    "evap.rewards",
    "evap.grades",
    "django.forms",
    "mozilla_django_oidc",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware should be here according to https://docs.djangoproject.com/en/2.2/topics/i18n/translation/#how-django-discovers-language-preference
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "mozilla_django_oidc.middleware.SessionRefresh",
    "evap.middleware.RequireLoginMiddleware",
    "evap.middleware.user_language_middleware",
    "evap.staff.staff_mode.staff_mode_middleware",
    "evap.evaluation.middleware.LoggingRequestMiddleware",
]

_TEMPLATE_OPTIONS = {
    "context_processors": [
        "django.contrib.auth.context_processors.auth",
        "django.template.context_processors.debug",
        "django.template.context_processors.i18n",
        "django.template.context_processors.static",
        "django.template.context_processors.request",
        "django.contrib.messages.context_processors.messages",
        "evap.context_processors.slogan",
        "evap.context_processors.debug",
        "evap.context_processors.notebook_form",
        "evap.context_processors.allow_anonymous_feedback_messages",
    ],
    "builtins": ["django.templatetags.i18n"],
}


TEMPLATES: Any = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": _TEMPLATE_OPTIONS,
        "NAME": "MainEngine",
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {**_TEMPLATE_OPTIONS, "debug": False},
        "NAME": "CachedEngine",  # used for bulk-filling caches
    },
]

# This allows to redefine form widget templates used by Django when generating forms.
# The templates are located in evaluation/templates/django/forms/widgets and add the "form-control" class for correct bootstrap styling.
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

AUTHENTICATION_BACKENDS = [
    "evap.evaluation.auth.RequestAuthUserBackend",
    "evap.evaluation.auth.OpenIDAuthenticationBackend",
    "evap.evaluation.auth.EmailAuthenticationBackend",
    "django.contrib.auth.backends.ModelBackend",
]

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

ROOT_URLCONF = "evap.urls"

WSGI_APPLICATION = "evap.wsgi.application"

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

LOGIN_URL = "/"

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "sessions"

SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365  # one year

STAFF_MODE_TIMEOUT = 3 * 60 * 60  # three hours
STAFF_MODE_INFO_TIMEOUT = 3 * 60 * 60  # three hours

### Internationalization

LANGUAGE_CODE = "en"

TIME_ZONE = "Europe/Berlin"

USE_I18N = True

USE_TZ = False

LOCALE_PATHS = [os.path.join(BASE_DIR, "locale")]

FORMAT_MODULE_PATH = ["evap.locale"]

LANGUAGES = [
    ("en", "English"),
    ("de", "Deutsch"),
]


### Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

STATIC_URL = "/static/"

# Additional locations of static files
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

# Absolute path to the directory static files should be collected to.
STATIC_ROOT = os.path.join(BASE_DIR, "static_collected")


### User-uploaded files

# Absolute filesystem path to the directory that will hold user-uploaded files.
MEDIA_ROOT = os.path.join(BASE_DIR, "upload")


### Slogans
SLOGANS_DE = [
    "Evaluierungen verlässlich ausführen und präsentieren",
    "Entscheidungsgrundlage zur Verbesserung akademischer Programme",
    "Ein voll atemberaubendes Projekt",
    "Evaluierungs-Vereinfachung aus Potsdam",
    "Elegante Verwaltung automatisierter Performancemessungen",
    "Effektive Vermeidung von anstrengendem Papierkram",
    "Einfach Verantwortlichen Abstimmungsergebnisse präsentieren",
    "Ein Vorzeigeprojekt auf Python-Basis",
    "Erleichtert Verfolgung aufgetretener Probleme",
    "Entwickelt von arbeitsamen Personen",
]
SLOGANS_EN = [
    "Extremely valuable automated processing",
    "Exploring various answers professionally",
    "Encourages values and perfection",
    "Enables virtuously adressed petitions",
    "Evades very annoying paperwork",
    "Engineered voluntarily and passionately",
    "Elegant valiantly administered platform",
    "Efficient voting and processing",
    "Everyone values awesome products",
    "Enhances vibrant academic programs",
]


### Allowed chosen first names / display names
def CHARACTER_ALLOWED_IN_NAME(character):  # pylint: disable=invalid-name
    return any(
        (
            ord(character) in range(32, 127),  # printable ASCII / Basic Latin characters
            ord(character) in range(160, 256),  # printable Latin-1 Supplement characters
            ord(character) in range(256, 384),  # Latin Extended-A
        )
    )


### OpenID Login
# replace 'example.com', OIDC_RP_CLIENT_ID and OIDC_RP_CLIENT_SECRET with real values in localsettings when activating
ACTIVATE_OPEN_ID_LOGIN = False
OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = 60 * 60 * 24 * 7  # one week
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_USERNAME_ALGO = ""
OIDC_RP_SCOPES = "openid email profile"

OIDC_RP_CLIENT_ID = "evap"
OIDC_RP_CLIENT_SECRET = "evap-secret"  # nosec

OIDC_OP_AUTHORIZATION_ENDPOINT = "https://example.com/auth"
OIDC_OP_TOKEN_ENDPOINT = "https://example.com/token"  # nosec
OIDC_OP_USER_ENDPOINT = "https://example.com/me"
OIDC_OP_JWKS_ENDPOINT = "https://example.com/certs"


### Other

# Create a localsettings.py if you want to locally override settings
# and don't want the changes to appear in 'git status'.
try:
    # if a localsettings file exists (vagrant), this will cause wildcard-import errors
    # if it does not, (GitHub), it would cause useless-suppression
    # pylint: disable=unused-wildcard-import,wildcard-import,useless-suppression

    # the import can overwrite locals with a slightly different type (e.g. DATABASES), which is fine.
    from evap.localsettings import *  # type: ignore
except ImportError:
    pass

TESTING = "test" in sys.argv or "pytest" in sys.modules

# speed up tests and activate typeguard introspection
if TESTING:
    from typeguard import install_import_hook

    install_import_hook(("evap", "tools"))

    # do not use ManifestStaticFilesStorage as it requires running collectstatic beforehand
    STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"

    logging.disable(logging.CRITICAL)  # disable logging, primarily to prevent console spam

    # use the database for caching. it's properly reset between tests in constrast to redis,
    # and does not change behaviour in contrast to disabling the cache entirely.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "testing_cache_default",
        },
        "results": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "testing_cache_results",
        },
        "sessions": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "testing_cache_sessions",
        },
    }
    from model_bakery import random_gen

    # give random char field values a reasonable length
    BAKER_CUSTOM_FIELDS_GEN = {"django.db.models.CharField": lambda: random_gen.gen_string(20)}


# Development helpers
if DEBUG:
    INSTALLED_APPS += ["evap.development"]

    # Django debug toolbar settings
    if not TESTING and ENABLE_DEBUG_TOOLBAR:
        INSTALLED_APPS += ["debug_toolbar"]
        MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

        def show_toolbar(request):
            return True

        DEBUG_TOOLBAR_CONFIG = {
            "SHOW_TOOLBAR_CALLBACK": "evap.settings.show_toolbar",
            "JQUERY_URL": "",
        }
