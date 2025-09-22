from evap.settings_resolver import derived

PAGE_URL = "localhost:8000"
ACTIVATE_OPEN_ID_LOGIN = False


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
