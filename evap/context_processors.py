import random

from django.conf import settings
from django.utils.translation import get_language


def slogan(request):
    if get_language() == "de":
        return {'SLOGAN': random.choice(settings.SLOGANS_DE)}  # nosec
    return {'SLOGAN': random.choice(settings.SLOGANS_EN)}  # nosec
