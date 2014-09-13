# Django settings for evap project.

# automatically determine SITE_ROOT, used for absolute paths below
import os.path
SITE_ROOT = os.path.dirname(os.path.realpath(__file__))

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    # ('Your Name', 'your_email@example.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3', # 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': os.path.join(SITE_ROOT, 'database.sqlite3'), # Or path to database file if using sqlite3.
        'USER': '',                             # Not used with sqlite3.
        'PASSWORD': '',                         # Not used with sqlite3.
        'HOST': '',                             # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                             # Set to empty string for default. Not used with sqlite3.
    }
}

CACHES = {
    'default': {
    #    'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# config for feedback links
FEEDBACK_EMAIL = "webmaster@localhost"
TRACKER_URL = "https://github.com/fsr-itse/EvaP"

# config for mail system
DEFAULT_FROM_EMAIL = "webmaster@localhost"
REPLY_TO_EMAIL = DEFAULT_FROM_EMAIL
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# key authentication settings
LOGIN_KEY_VALIDITY = 210 # days, so roughly 7 months

# minimum answers needed for publishing
MIN_ANSWER_COUNT = 2
MIN_ANSWER_PERCENTAGE = 0.2

# a warning is shown next to results where less than this percentage of the median number of answers (for this question in this course) were given
RESULTS_WARNING_PERCENTAGE = 0.5

# the final total grade will be calculated by the following formula (GP = GRADE_PERCENTAGE, CP = CONTRIBUTION_PERCENTAGE):
# final_likert = CP * likert_answers_about_persons + (1-CP) * likert_answers_about_courses
# final_grade = CP * grade_answers_about_persons + (1-CP) * grade_answers_about_courses
# final = GP * final_grade + (1-GP) * final_likert
GRADE_PERCENTAGE = 0.8
CONTRIBUTION_PERCENTAGE = 0.5

# days before end date to send reminder
REMIND_X_DAYS_AHEAD_OF_END_DATE = 2

# email domains for the internal users of the hosting institution used to
# figure out who can login with username and password and who needs a login key
INSTITUTION_EMAIL_DOMAINS = ["hpi.uni-potsdam.de", "student.hpi.uni-potsdam.de"]

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'Europe/Berlin'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en'

LANGUAGES = (
    ('en', "English"),
    ('de', "Deutsch"),
)

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale
USE_L10N = True

# Locale paths
LOCALE_PATHS = (
    os.path.join(SITE_ROOT, "locale"),
)

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
MEDIA_ROOT = os.path.join(SITE_ROOT, "upload")

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = os.path.join(SITE_ROOT, "staticfiles")

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '/static/'

# URL prefix for admin static files -- CSS, JavaScript and images.
# Make sure to use a trailing slash.
# Examples: "http://foo.com/static/admin/", "/static/admin/".
ADMIN_MEDIA_PREFIX = '/static/admin/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    os.path.join(SITE_ROOT, "static"),
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'k9-)vh3c_dtm6bpi7j(!*s_^91v0!ekjt_#o&0i$e22tnn^-vb'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    "django.contrib.auth.context_processors.auth",
    "django.core.context_processors.debug",
    "django.core.context_processors.i18n",
    "django.core.context_processors.media",
    "django.core.context_processors.static",
    "django.core.context_processors.request",
    "django.contrib.messages.context_processors.messages",
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'evap.evaluation.auth.RequestAuthMiddleware',
    'evap.evaluation.403.Django403Middleware',
)

AUTHENTICATION_BACKENDS = (
    'evap.evaluation.auth.RequestAuthUserBackend',
    'django.contrib.auth.backends.ModelBackend',
)


# redirect url after login
LOGIN_REDIRECT_URL = '/'

LOGIN_URL = "/"

ROOT_URLCONF = 'evap.urls'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    os.path.join(SITE_ROOT, "templates"),
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'south',
    'widget_tweaks',
    'evap.evaluation',
    'evap.fsr',
    'evap.results',
    'evap.student',
    'evap.contributor',
)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
         'require_debug_false': {
             '()': 'django.utils.log.RequireDebugFalse'
         }
     },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler'
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        'evap.evaluation.management.commands.import_evaj': {
            'handlers': ['console'],
            'level': 'INFO'
        }
    }
}

# kerberos realm and service
ENABLE_KERBEROS = False
if (ENABLE_KERBEROS):
    KRB5_REALM = 'EXAMPLE.COM'
    KRB5_SERVICE = 'krbtgt@AS.EXAMPLE.COM'
    INSTALLED_APPS += ('django_auth_kerberos',)
    MIDDLEWARE_CLASSES += ('django_auth_kerberos.backends.KrbBackend',)

#django debug toolbar settings
ENABLE_DEBUG_TOOLBAR = False
if DEBUG and ENABLE_DEBUG_TOOLBAR:
    DEBUG_TOOLBAR_PATCH_SETTINGS = False
    INSTALLED_APPS += ('debug_toolbar',)
    MIDDLEWARE_CLASSES = ('debug_toolbar.middleware.DebugToolbarMiddleware',) + MIDDLEWARE_CLASSES
    def show_toolbar(request):
        return True
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': 'evap.settings.show_toolbar',
    }

# Create a localsettings.py if you want to override settings per machine
# or user, e.g. for development or different settings in deployments using
# multiple servers.
_LOCAL_SETTINGS_FILENAME = os.path.join(SITE_ROOT, "localsettings.py")
if os.path.exists(_LOCAL_SETTINGS_FILENAME):
    execfile(_LOCAL_SETTINGS_FILENAME)
del _LOCAL_SETTINGS_FILENAME
