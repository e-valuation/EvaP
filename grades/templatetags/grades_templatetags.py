from django.template import Library

from evap.evaluation.models import Semester

register = Library()


@register.inclusion_tag("grades_semester_menu.html")
def include_grades_semester_menu():
    return dict(semesters=Semester.objects.all()[:5])
