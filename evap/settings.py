"""
Django settings for EvaP project.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.0/ref/settings/
"""

import os
import sys
import logging

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

# percentages for calculating an evaluation's total average grade
CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT = 4  # grade questions are weighted this much for each contributor's average grade
CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT = 6  # non-grade questions are weighted this much for each contributor's average grade
CONTRIBUTIONS_WEIGHT = 1  # the average contribution grade is weighted this much for the evaluation's average grade
GENERAL_GRADE_QUESTIONS_WEIGHT = 1  # the average grade of all general grade questions is weighted this much for the evaluation's average grade
GENERAL_NON_GRADE_QUESTIONS_WEIGHT = 1  # the average grade of all general non-grade questions is weighted this much for the evaluation's average grade

# number of reward points a student should have for a semester after evaluating the given fraction of evaluations.
REWARD_POINTS = [
    (1 / 3, 1),
    (2 / 3, 2),
    (3 / 3, 3),
]

# days before end date to send reminder
REMIND_X_DAYS_AHEAD_OF_END_DATE = [2, 0]

# email domains for the internal users of the hosting institution used to
# figure out who can login with username and password and who needs a login key
INSTITUTION_EMAIL_DOMAINS = ["institution.example.com"]

INTERNAL_USERNAMES_MAX_LENGTH = 20

# List of tuples defining email domains that should be replaced on saving UserProfiles.
# Emails ending on the first value will have this part replaced by the second value.
# e.g.: [("institution.example.com", "institution.com")]
INSTITUTION_EMAIL_REPLACEMENTS = []

# the importer accepts only these two strings in the 'graded' column
IMPORTER_GRADED_YES = "yes"
IMPORTER_GRADED_NO = "no"

# the importer will warn if any participant has more enrollments than this number
IMPORTER_MAX_ENROLLMENTS = 7

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
ADMINS = [
    # ('Your Name', 'your_email@example.com'),
]

# The page URL that is used in email templates.
PAGE_URL = "localhost:8000"

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'k9-)vh3c_dtm6bpi7j(!*s_^91v0!ekjt_#o&0i$e22tnn^-vb'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',  # postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'evap',  # Or path to database file if using sqlite3.
        'USER': 'postgres',                              # Not used with sqlite3.
        'PASSWORD': '',                          # Not used with sqlite3.
        'HOST': '',                              # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                              # Set to empty string for default. Not used with sqlite3.
        'CONN_MAX_AGE': 600,
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/0',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'MAX_ENTRIES': 5000
        }
    },
    'results': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'TIMEOUT': None,  # is always invalidated manually
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'MAX_ENTRIES': 100000
        }
    },
    'sessions': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/2',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'MAX_ENTRIES': 5000
        }
    },
}

CONTACT_EMAIL = "webmaster@localhost"

# Config for mail system
DEFAULT_FROM_EMAIL = "webmaster@localhost"
REPLY_TO_EMAIL = DEFAULT_FROM_EMAIL
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s: %(message)s',
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR + '/logs/evap.log',
            'maxBytes': 1024 * 1024 * 10,
            'backupCount': 5,
            'formatter': 'default',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file', 'mail_admins'],
            'level': 'INFO',
            'propagate': True,
        },
        'evap': {
            'handlers': ['console', 'file', 'mail_admins'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'mozilla_django_oidc': {
            'handlers': ['console', 'file', 'mail_admins'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}


### Application definition

AUTH_USER_MODEL = 'evaluation.UserProfile'

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'compressor',
    'django_extensions',
    'evap.evaluation',
    'evap.staff',
    'evap.results',
    'evap.student',
    'evap.contributor',
    'evap.rewards',
    'evap.grades',
    'django.forms',
    'mozilla_django_oidc',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # LocaleMiddleware should be here according to https://docs.djangoproject.com/en/2.2/topics/i18n/translation/#how-django-discovers-language-preference
    # Furthermore, set_or_get_language (happens on login) uses the active language, so LocaleMiddleware should be before AuthenticationMiddleware
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'mozilla_django_oidc.middleware.SessionRefresh',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.static",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "evap.context_processors.slogan"
            ],
            'builtins': ['django.templatetags.i18n'],
        },
    },
]

# This allows to redefine form widget templates used by Django when generating forms.
# The templates are located in evaluation/templates/django/forms/widgets and add the "form-control" class for correct bootstrap styling.
FORM_RENDERER = 'django.forms.renderers.TemplatesSetting'

AUTHENTICATION_BACKENDS = [
    'evap.evaluation.auth.RequestAuthUserBackend',
    'evap.evaluation.auth.OpenIDAuthenticationBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'evap.urls'

WSGI_APPLICATION = 'evap.wsgi.application'

# Redirect url after login
LOGIN_REDIRECT_URL = '/'

LOGIN_URL = "/"

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "sessions"

SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365  # one year


### Internationalization

LANGUAGE_CODE = 'en'

TIME_ZONE = 'Europe/Berlin'

USE_I18N = True

USE_L10N = True

USE_TZ = False

LOCALE_PATHS = [os.path.join(BASE_DIR, 'locale')]

FORMAT_MODULE_PATH = ['evap.locale']

LANGUAGES = [
    ('en', "English"),
    ('de', "Deutsch"),
]

USERNAME_REPLACEMENTS = [
    (' ', ''),
    ('ä', 'ae'),
    ('ö', 'oe'),
    ('ü', 'ue'),
    ('ß', 'ss'),
]


### Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

STATIC_URL = '/static/'

# Additional locations of static files
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
]

# Absolute path to the directory static files should be collected to.
STATIC_ROOT = os.path.join(BASE_DIR, "static_collected")

# django-compressor settings
COMPRESS_ENABLED = not DEBUG
COMPRESS_OFFLINE = False
COMPRESS_PRECOMPILERS = (
    ('text/x-scss', 'sass {infile} {outfile}'),
)
COMPRESS_CACHEABLE_PRECOMPILERS = ('text/x-scss',)


### User-uploaded files

# Absolute filesystem path to the directory that will hold user-uploaded files.
MEDIA_ROOT = os.path.join(BASE_DIR, "upload")

# the backend used for downloading attachments
# see https://github.com/johnsensible/django-sendfile for further information
SENDFILE_BACKEND = 'sendfile.backends.simple'


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


### OpenID Login
# replace 'example.com', OIDC_RP_CLIENT_ID and OIDC_RP_CLIENT_SECRET with real values in localsettings when activating
ACTIVATE_OPEN_ID_LOGIN = False
OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = 60 * 60 * 24 * 7  # one week
OIDC_RP_SIGN_ALGO = 'RS256'
OIDC_USERNAME_ALGO = ''
OIDC_RP_SCOPES = 'openid email profile'
LOGOUT_REDIRECT_URL = '/'

OIDC_RP_CLIENT_ID = 'evap'
OIDC_RP_CLIENT_SECRET = 'evap-secret'

OIDC_OP_AUTHORIZATION_ENDPOINT = "https://example.com/auth"
OIDC_OP_TOKEN_ENDPOINT = "https://example.com/token"
OIDC_OP_USER_ENDPOINT = "https://example.com/me"
OIDC_OP_JWKS_ENDPOINT = "https://example.com/certs"


### Other

# Create a localsettings.py if you want to locally override settings
# and don't want the changes to appear in 'git status'.
try:
    from evap.localsettings import *
except ImportError:
    pass

TESTING = 'test' in sys.argv

# speed up tests
if TESTING:
    COMPRESS_PRECOMPILERS = ()  # disable django-compressor
    logging.disable(logging.CRITICAL)  # disable logging, primarily to prevent console spam
    # use the database for caching. it's properly reset between tests in constrast to redis,
    # and does not change behaviour in contrast to disabling the cache entirely.
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'testing_cache_default',
        },
        'results': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'testing_cache_results',
        },
        'sessions': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'testing_cache_sessions',
        },
    }
    # give random char field values a reasonable length
    from model_mommy import random_gen
    MOMMY_CUSTOM_FIELDS_GEN = {'django.db.models.CharField': lambda: random_gen.gen_string(20)}


# Django debug toolbar settings
if DEBUG and not TESTING and ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
    def show_toolbar(request):
        return True
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': 'evap.settings.show_toolbar',
        'JQUERY_URL': '',
    }
