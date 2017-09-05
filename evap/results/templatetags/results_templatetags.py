from django.template import Library
from evap.results.tools import get_grade_color, get_deviation_color

register = Library()


@register.filter(name='gradecolor')
def gradecolor(grade):
    return 'rgb({}, {}, {})'.format(*get_grade_color(grade))


@register.filter(name='deviationcolor')
def deviationcolor(deviation):
    return 'rgb({}, {}, {})'.format(*get_deviation_color(deviation))
