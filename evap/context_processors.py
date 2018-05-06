from django.conf import settings
from django.utils.translation import get_language

import random


def slogan(request):
    if get_language() == "de":
        return {'SLOGAN': random.choice(settings.SLOGANS_DE)}
    return {'SLOGAN': random.choice(settings.SLOGANS_EN)}
