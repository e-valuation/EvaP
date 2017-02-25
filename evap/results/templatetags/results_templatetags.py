from django.template import Library
from evap.evaluation.models import Semester
from evap.results.tools import get_grade_color, get_deviation_color

register = Library()


@register.inclusion_tag("results_semester_menu.html")
def include_results_semester_menu():
    return dict(semesters=Semester.get_all_with_published_courses())


@register.filter(name='gradecolor')
def gradecolor(grade):
    return 'rgb({}, {}, {})'.format(*get_grade_color(grade))


@register.filter(name='deviationcolor')
def deviationcolor(deviation):
    return 'rgb({}, {}, {})'.format(*get_deviation_color(deviation))
