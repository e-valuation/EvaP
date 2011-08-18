from django import template
from evaluation.models import Semester, QuestionGroup

register = template.Library()

@register.inclusion_tag('fsr_semester_menu.html')
def show_semesters():
    semesters = Semester.objects.all()
    return {'semesters': semesters}

@register.inclusion_tag('fsr_questiongroup_menu.html')
def show_questiongroups():
    questiongroups = QuestionGroup.objects.all()
    return {'questiongroups': questiongroups}