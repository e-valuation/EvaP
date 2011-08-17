from django import template
from evaluation.models import Semester

register = template.Library()

@register.inclusion_tag('fsr_semester_menu.html')
def show_semesters():
    semesters = Semester.objects.all()
    return {'semesters': semesters}