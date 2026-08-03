from django.template import Library
from django.urls import reverse
from django.utils.html import format_html

from evap.staff.forms import ExamEvaluationForm

register = Library()


@register.filter(name="create_exam_evaluation_form")
def create_exam_evaluation_form(evaluation):
    form_id = f"exam_creation_form_{evaluation.id}"
    return ExamEvaluationForm(None, evaluation=evaluation, form_id=form_id)


@register.simple_block_tag(takes_context=True)
def breadcrumb_item(context, content):
    return breadcrumb_item_url(context, content, None)


@register.simple_block_tag(takes_context=True)
def breadcrumb_item_url(context, content, url_path, *args, fragment=None):
    url = reverse(url_path, args=args, fragment=fragment) if url_path is not None else None

    request = context["request"]
    current_path = request.path

    if url is None or current_path == url:
        return format_html(
            '<li class="breadcrumb-item">{}</li>',
            content,
        )

    return format_html(
        '<li class="breadcrumb-item"><a href="{}">{}</a></li>',
        url,
        content,
    )
