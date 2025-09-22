from fractions import Fraction

from django.utils.safestring import mark_safe

from evap.settings_resolver import derived

PAGE_URL = "localhost:8000"
ACTIVATE_OPEN_ID_LOGIN = False

# Make apache work when DEBUG == False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]


@derived(prev={"INSTALLED_APPS"}, final={"DEBUG"})
def INSTALLED_APPS(prev, final):
    if final.DEBUG:
        return prev.INSTALLED_APPS + ["evap.development"]
    return prev.INSTALLED_APPS


CONTACT_EMAIL = "webmaster@localhost"
DEFAULT_FROM_EMAIL = "webmaster@localhost"
REPLY_TO_EMAIL = DEFAULT_FROM_EMAIL
SEND_ALL_EMAILS_TO_ADMINS_IN_BCC = False

LEGAL_NOTICE_TEXT = "Objection! (this is a default setting that the administrators should change, please contact them)"

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
# Questionnaires automatically added to exam evaluations
EXAM_QUESTIONNAIRE_IDS = [111]
