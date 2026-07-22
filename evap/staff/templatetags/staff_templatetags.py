from django.template import Library

from evap.staff.forms import ExamEvaluationForm

register = Library()


@register.filter(name="create_exam_evaluation_form")
def create_exam_evaluation_form(evaluation):
    prefix = f"exam_creation_{evaluation.pk}"
    return ExamEvaluationForm(evaluation=evaluation, prefix=prefix, form_id=prefix)
