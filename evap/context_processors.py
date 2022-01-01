import random

from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.translation import get_language


def slogan(request):
    if get_language() == "de":
        return {"slogan": random.choice(settings.SLOGANS_DE)}  # nosec
    return {"slogan": random.choice(settings.SLOGANS_EN)}  # nosec


def debug(request):
    return {"debug": settings.DEBUG}


def set_csrf_cookie(request):
    # this does not add anything to the context, but ensures that the
    # csrf cookie is set in every view. It is only set if
    # get_token is called, which we don't do in our templates anymore.
    get_token(request)
    return {}
