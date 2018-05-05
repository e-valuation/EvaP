from django.template import Library
from evap.results.tools import get_grade_color, normalized_distribution

register = Library()


@register.filter(name='gradecolor')
def gradecolor(grade):
    return 'rgb({}, {}, {})'.format(*get_grade_color(grade))


@register.filter(name='normalized_distribution')
def norm_distribution(distribution):
    return normalized_distribution(distribution)
