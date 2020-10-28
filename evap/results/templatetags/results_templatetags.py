from django.template import Library
from evap.results.tools import get_grade_color, normalized_distribution, STATES_WITH_RESULT_TEMPLATE_CACHING

register = Library()


@register.filter(name='gradecolor')
def gradecolor(grade):
    return 'rgb({}, {}, {})'.format(*get_grade_color(grade))


@register.filter(name='normalized_distribution')
def norm_distribution(distribution):
    return normalized_distribution(distribution)


@register.filter(name='evaluation_results_cache_timeout')
def evaluation_results_cache_timeout(evaluation):
    if evaluation.state in STATES_WITH_RESULT_TEMPLATE_CACHING:
        return None  # cache forever
    return 0  # don't cache at all


@register.filter(name='participationclass')
def participationclass(number_of_voters, number_of_participants):
    return round((number_of_voters/number_of_participants)*10)
