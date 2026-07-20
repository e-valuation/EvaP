from django.conf import settings
from django.template import Library

register = Library()


@register.simple_tag
def release_version():
    return settings.RELEASE_VERSION


@register.simple_tag
def legal_link():
    return settings.LEGAL_NOTICE_LINK
