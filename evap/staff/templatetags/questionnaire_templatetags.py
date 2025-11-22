import json

from django.template import Library
from django.utils.safestring import SafeString, mark_safe

from evap.evaluation.models import Question
from evap.staff.forms import QuestionForm

register = Library()


@register.simple_tag
def load_question_text_options(language: SafeString) -> SafeString:
    values = Question.objects.all().values("id", *QuestionForm.Meta.fields)
    return mark_safe(json.dumps([{"value": json.dumps(value), "text": value[f"text_{language}"]} for value in values]))
