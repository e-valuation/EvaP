# -*- coding: utf-8 -*-
"""
Django settings for EvaP project.

For more information on this file, see
https://docs.djangoproject.com/en/1.7/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.7/ref/settings/
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

# key authentication settings
LOGIN_KEY_VALIDITY = 210  # days, so roughly 7 months

# minimum answers needed for publishing
MIN_ANSWER_COUNT = 2
MIN_ANSWER_PERCENTAGE = 0.2

# a warning is shown next to results where less than RESULTS_WARNING_COUNT answers were given
# or the number of answers is less than RESULTS_WARNING_PERCENTAGE times the median number of answers (for this question in this course)
RESULTS_WARNING_COUNT = 4
RESULTS_WARNING_PERCENTAGE = 0.5

# the final total grade will be calculated by the following formula (GP = GRADE_PERCENTAGE, CP = CONTRIBUTION_PERCENTAGE):
# final_likert = CP * likert_answers_about_persons + (1-CP) * likert_answers_about_courses
# final_grade = CP * grade_answers_about_persons + (1-CP) * grade_answers_about_courses
# final = GP * final_grade + (1-GP) * final_likert
GRADE_PERCENTAGE = 0.8
CONTRIBUTION_PERCENTAGE = 0.5

# number of reward points to be given to a student once all courses of a semester have been voted for
REWARD_POINTS_PER_SEMESTER = 3

# days before end date to send reminder
REMIND_X_DAYS_AHEAD_OF_END_DATE = [2, 0]

# email domains for the internal users of the hosting institution used to
# figure out who can login with username and password and who needs a login key
INSTITUTION_EMAIL_DOMAINS = ["institution.example.com"]

# maximum length of usernames of internal users
INTERNAL_USERNAMES_MAX_LENGTH = 20

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

### Installation specific settings

# People who get emails on errors.
ADMINS = [
    # ('Your Name', 'your_email@example.com'),
]

# These are listed for easier development. Remove them in production environments.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# The page URL that is used in email templates.
PAGE_URL = "localhost:8000"

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'k9-)vh3c_dtm6bpi7j(!*s_^91v0!ekjt_#o&0i$e22tnn^-vb'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',  # 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': os.path.join(BASE_DIR, 'database.sqlite3'),  # Or path to database file if using sqlite3.
        'USER': '',                              # Not used with sqlite3.
        'PASSWORD': '',                          # Not used with sqlite3.
        'HOST': '',                              # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                              # Set to empty string for default. Not used with sqlite3.
        'CONN_MAX_AGE': 600,
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'evap_db_cache',
        'OPTIONS': {
            'MAX_ENTRIES': 1000  # note that the results alone need one entry per course
        }
    }
}

# Config for feedback links
FEEDBACK_EMAIL = "webmaster@localhost"
TRACKER_URL = "https://github.com/fsr-itse/EvaP"

# Config for mail system
DEFAULT_FROM_EMAIL = "webmaster@localhost"
REPLY_TO_EMAIL = DEFAULT_FROM_EMAIL
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Config for legal notice
# The HTML file which should be used must be located in evap\templates\legal_notice_text.html
LEGAL_NOTICE_ACTIVE = False


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
    },
}


### Application definition

AUTH_USER_MODEL = 'evaluation.UserProfile'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'bootstrap3',
    'compressor',
    'django_extensions',
    'evap.evaluation',
    'evap.staff',
    'evap.results',
    'evap.student',
    'evap.contributor',
    'evap.rewards',
    'evap.grades',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'evap.evaluation.auth.RequestAuthMiddleware',
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
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "evap.context_processors.legal_notice_active",
                "evap.context_processors.tracker_url",
            ],
            'builtins': ['django.templatetags.i18n'],
        },
    },
]

AUTHENTICATION_BACKENDS = [
    'evap.evaluation.auth.RequestAuthUserBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'evap.urls'

WSGI_APPLICATION = 'evap.wsgi.application'

# Redirect url after login
LOGIN_REDIRECT_URL = '/'

LOGIN_URL = "/"


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

# Specify an offset that will be added to the evaluation end date (e.g. 3: If the end date is 01.01., the evaluation will end at 02.01. 03:00.).
EVALUATION_END_OFFSET_HOURS = 3

### Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.7/howto/static-files/

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


### User-uploaded files

# Absolute filesystem path to the directory that will hold user-uploaded files.
MEDIA_ROOT = os.path.join(BASE_DIR, "upload")

# URL that handles the media served from MEDIA_ROOT.
MEDIA_URL = '/media/'

# the backend used for downloading attachments
# see https://github.com/johnsensible/django-sendfile for further information
SENDFILE_BACKEND = 'sendfile.backends.simple'


### Other

# django-bootstrap3
BOOTSTRAP3 = {
    'horizontal_label_class': 'col-md-2',
    'horizontal_field_class': 'col-md-6',
}

# django-compressor settings
COMPRESS_ENABLED = not DEBUG
COMPRESS_OFFLINE = False
COMPRESS_PRECOMPILERS = (
    ('text/less', 'lessc {infile} {outfile}'),
)
COMPRESS_CACHEABLE_PRECOMPILERS = ('text/less',)

# Create a localsettings.py if you want to locally override settings
# and don't want the changes to appear in 'git status'.
try:
    from evap.localsettings import *
except ImportError:
    pass

TESTING = 'test' in sys.argv

# speed up tests
if TESTING:
    DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3'}  # use sqlite to speed tests up
    COMPRESS_PRECOMPILERS = ()  # disable django-compressor
    logging.disable(logging.CRITICAL)  # disable logging, primarily to prevent console spam


# Django debug toolbar settings
if DEBUG and not TESTING and ENABLE_DEBUG_TOOLBAR:
    DEBUG_TOOLBAR_PATCH_SETTINGS = False
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
    def show_toolbar(request):
        return True
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': 'evap.settings.show_toolbar',
    }
