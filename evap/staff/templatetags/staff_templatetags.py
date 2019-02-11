from django.template import Library

from evap.staff.importers import WARNING_DESCRIPTIONS

register = Library()


@register.filter(name='warningname')
def warningname(warning):
    return WARNING_DESCRIPTIONS.get(warning)
