from django.template import Library

from evap.evaluation.models import Semester

register = Library()


@register.inclusion_tag("staff_semester_menu.html")
def include_staff_semester_menu():
    return dict(semesters=Semester.objects.all()[:5])


@register.inclusion_tag('staff_user_labels.html')
def include_staff_user_labels(user):
    return dict(user=user)


@register.inclusion_tag("staff_questionnaire_index_list.html")
def include_staff_questionnaire_index_list(questionnaires, headline):
    return dict(questionnaires=questionnaires, headline=headline)


@register.inclusion_tag("staff_semester_view_course.html")
def include_staff_semester_view_course(semester, course, disable_if_archived, info_only=False):
    return dict(semester=semester, course=course, disable_if_archived=disable_if_archived, info_only=info_only)
