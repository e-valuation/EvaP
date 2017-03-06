from django.template import Library
from evap.evaluation.models import Semester

register = Library()


@register.inclusion_tag("results_semester_menu.html")
def include_results_semester_menu():
    return dict(semesters=Semester.get_all_with_published_courses())
