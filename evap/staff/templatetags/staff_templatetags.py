from django.template import Library
from django.utils.safestring import mark_safe

from evap.staff.forms import ExamEvaluationForm

register = Library()


@register.filter(name="create_exam_evaluation_form")
def create_exam_evaluation_form(evaluation):
    form_id = f"exam_creation_form_{evaluation.id}"
    return ExamEvaluationForm(None, evaluation=evaluation, form_id=form_id)


@register.simple_block_tag(takes_context=True)
def create_breadcrumb(context, content, url=None):
    request = context["request"]
    current_path = request.path
    if url is None or current_path == url:
        html = f'<li class="breadcrumb-item">{content}</li>'
    else:
        # create the href="link" string.
        href_str = f'href="{url}"'
        html = f'<li class="breadcrumb-item"><a {href_str}>{content}</a></li>'
    return mark_safe(html)
