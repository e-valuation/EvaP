from django.template import Library

from evap.staff.forms import ExamEvaluationForm

register = Library()


@register.filter(name="create_exam_evaluation_form")
def create_exam_evaluation_form(evaluation):
    form_id = f"exam_creation_form_{evaluation.id}"
    return ExamEvaluationForm(None, evaluation=evaluation, form_id=form_id)
