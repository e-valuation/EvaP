import os.path
import sys
from django.contrib.messages import constants as messages

SITE_ROOT = os.path.dirname(os.path.realpath(__file__))

DEBUG = True
TEMPLATE_DEBUG = DEBUG
TESTING = 'test' in sys.argv

AUTH_USER_MODEL = 'evaluation.UserProfile'

MESSAGE_TAGS = {
    messages.ERROR: 'danger',
}

# People who get emails on errors.
ADMINS = (
    # ('Your Name', 'your_email@example.com'),
)

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

# number of reward points to be given to a student once all courses of a semester have been voted for
REWARD_POINTS_PER_SEMESTER = 3

# days before end date to send reminder
REMIND_X_DAYS_AHEAD_OF_END_DATE = [2, 0]

# email domains for the internal users of the hosting institution used to
# figure out who can login with username and password and who needs a login key
INSTITUTION_EMAIL_DOMAINS = ["hpi.uni-potsdam.de", "student.hpi.uni-potsdam.de", "hpi.de", "student.hpi.de"]

# maximum length of usernames of internal users
INTERNAL_USERNAMES_MAX_LENGTH = 20

IMPORTER_GRADED_YES = "yes"
IMPORTER_GRADED_NO = "no"

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

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    os.path.join(SITE_ROOT, "static"),
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'k9-)vh3c_dtm6bpi7j(!*s_^91v0!ekjt_#o&0i$e22tnn^-vb'

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
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.sites', # unused. left here to not break the test data.
    'widget_tweaks',
    'evap.evaluation',
    'evap.staff',
    'evap.results',
    'evap.student',
    'evap.contributor',
    'evap.rewards',
)

# kerberos realm and service
ENABLE_KERBEROS = False
if (ENABLE_KERBEROS):
    KRB5_REALM = 'EXAMPLE.COM'
    KRB5_SERVICE = 'krbtgt@AS.EXAMPLE.COM'
    INSTALLED_APPS += ('django_auth_kerberos',)
    MIDDLEWARE_CLASSES += ('django_auth_kerberos.backends.KrbBackend',)

# django debug toolbar settings
ENABLE_DEBUG_TOOLBAR = False
if DEBUG and not TESTING and ENABLE_DEBUG_TOOLBAR:
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
    exec(compile(open(_LOCAL_SETTINGS_FILENAME).read(), _LOCAL_SETTINGS_FILENAME, 'exec'))
del _LOCAL_SETTINGS_FILENAME
