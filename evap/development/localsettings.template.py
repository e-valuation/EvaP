# noqa: N999

from fractions import Fraction
from pathlib import Path

from django.utils.safestring import mark_safe

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "evap",
        "USER": "evap",
        "PASSWORD": "evap",
        # Absolute path to use unix domain socket
        "HOST": Path("./data/").resolve(),
        "CONN_MAX_AGE": 600,
    }
}

REDIS_URL = f"unix://{Path('./data/redis.socket').resolve()}"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}?db=0",
    },
    "results": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}?db=1",
        "TIMEOUT": None,  # is always invalidated manually
    },
    "sessions": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}?db=2",
    },
}

# Make this unique, and don't share it with anybody.
SECRET_KEY = "$SECRET_KEY"  # nosec

# Make apache work when DEBUG == False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

### Evaluation progress rewards
GLOBAL_EVALUATION_PROGRESS_REWARDS: list[tuple[Fraction, dict[str, str]]] = [
    (Fraction("0"), {"de": "0 €", "en": "0€"}),
    (Fraction("0.25"), {"de": "1.000 €", "en": "1,000€"}),
    (Fraction("0.6"), {"de": "3.000 €", "en": "3,000€"}),
    (Fraction("0.7"), {"de": "7.000 €", "en": "7,000€"}),
    (Fraction("0.9"), {"de": "10.000 €", "en": "10,000€"}),
]
GLOBAL_EVALUATION_PROGRESS_EXCLUDED_COURSE_TYPE_IDS: list[int] = []
GLOBAL_EVALUATION_PROGRESS_EXCLUDED_EVALUATION_IDS: list[int] = []
GLOBAL_EVALUATION_PROGRESS_CAMPAIGN: dict[str, str] = {
    "title_de": "Spendenaktion",
    "title_en": "Fundraising",
    "info_title_de": "Jede Stimme zählt! Erfahre mehr über unser Spendenziel.",
    "info_title_en": "Every vote counts! Read more about our fundraising goal.",
    "info_text_de": mark_safe("Deine Teilnahme am Evaluationsprojekt wird helfen. Evaluiere also <b>jetzt</b>!"),
    "info_text_en": mark_safe("Your participation in the evaluation helps, so evaluate <b>now</b>!"),
}

# Questionnaires automatically added to exam evaluations
EXAM_QUESTIONNAIRE_IDS = [111]
