from importlib.metadata import version

from django.template import Library

register = Library()


@register.simple_tag
def release_version():
    return version("evap")
