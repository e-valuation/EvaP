from fractions import Fraction

from django.utils.safestring import mark_safe

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'evap',
        'USER': 'evap',
        'PASSWORD': 'evap',
        'HOST': '127.0.0.1',                    # Set to empty string for localhost.
        'PORT': '',                             # Set to empty string for default.
        'CONN_MAX_AGE': 600,
    }
}

# Make this unique, and don't share it with anybody.
SECRET_KEY = "${SECRET_KEY}"  # nosec

# Make apache work when DEBUG == False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

### Evaluation progress rewards
GLOBAL_EVALUATION_PROGRESS_REWARDS: list[tuple[Fraction, str]] = [
    (Fraction("0"), "0€"),
    (Fraction("0.25"), "1.000€"),
    (Fraction("0.6"), "3.000€"),
    (Fraction("0.7"), "7.000€"),
    (Fraction("0.9"), "10.000€"),
]
GLOBAL_EVALUATION_PROGRESS_EXCLUDED_COURSE_TYPE_IDS: list[int] = []
GLOBAL_EVALUATION_PROGRESS_EXCLUDED_EVALUATION_IDS: list[int] = []
GLOBAL_EVALUATION_PROGRESS_INFO_TEXT = {
    "de": mark_safe("Deine Teilnahme am Evaluationsprojekt wird helfen. Evaluiere also <b>jetzt</b>!"),
    "en": mark_safe("Your participation in the evaluation helps, so evaluate <b>now</b>!"),
}
