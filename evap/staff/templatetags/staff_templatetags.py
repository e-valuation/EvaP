from django.template import Library

from evap.evaluation.models import Semester
from evap.staff.importers import WARNING_DESCRIPTIONS

register = Library()


@register.inclusion_tag("staff_semester_menu.html")
def include_staff_semester_menu(indentation=False):
    return {
        'semesters': Semester.objects.all()[:5],
        'indentation': indentation,
    }


@register.filter(name='warningname')
def warningname(warning):
    return WARNING_DESCRIPTIONS.get(warning)
