from typing import Any, Iterable

from django.template import Library

from evap.results.tools import (
    STATES_WITH_RESULT_TEMPLATE_CACHING,
    RatingResult,
    get_grade_color,
    normalized_distribution,
)

register = Library()


@register.filter(name="gradecolor")
def gradecolor(grade):
    return "rgb({}, {}, {})".format(*get_grade_color(grade))  # pylint: disable=consider-using-f-string


@register.filter(name="normalized_distribution")
def norm_distribution(distribution):
    return normalized_distribution(distribution)


@register.filter(name="evaluation_results_cache_timeout")
def evaluation_results_cache_timeout(evaluation):
    if evaluation.state in STATES_WITH_RESULT_TEMPLATE_CACHING:
        return None  # cache forever
    return 0  # don't cache at all


@register.filter(name="participationclass")
def participationclass(number_of_voters, number_of_participants):
    return round((number_of_voters / number_of_participants) * 10)


@register.filter
def has_answers(rating_result: RatingResult):
    return RatingResult.has_answers(rating_result)


@register.filter
def is_published(rating_result: RatingResult):
    return RatingResult.is_published(rating_result)


@register.filter
def voters_order(evaluation) -> str:
    """float to string conversion done in python to circumvent localization breaking number parsing"""
    return str(evaluation.voter_ratio)


@register.filter
def aggregated_voters_order(evaluations: Iterable[Any]) -> str:
    return str(max(evaluation.voter_ratio for evaluation in evaluations))
