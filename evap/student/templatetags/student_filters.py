from collections.abc import Iterable

from django.template import Library

from evap.student.models import TextAnswerWarning

register = Library()


@register.filter
def text_answer_warning_trigger_strings(text_answer_warnings: Iterable[TextAnswerWarning]) -> list[list[str]]:
    return [text_answer_warning.trigger_strings for text_answer_warning in text_answer_warnings]
