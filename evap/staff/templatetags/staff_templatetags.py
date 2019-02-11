from django.template import Library

from evap.staff.importers import WARNING_DESCRIPTIONS

from django.utils.translation import ugettext_lazy as _

register = Library()


@register.filter(name='warningname')
def warningname(warning):
    return _(WARNING_DESCRIPTIONS.get(warning))
