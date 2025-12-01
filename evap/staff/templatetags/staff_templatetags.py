from django.template import Library

from evap.staff.forms import ExamEvaluationForm

register = Library()


@register.filter(name="create_exam_evaluation_form")
def create_exam_evaluation_form(evaluation):
    return ExamEvaluationForm(None, evaluation=evaluation)
