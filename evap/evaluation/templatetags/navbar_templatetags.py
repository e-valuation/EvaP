from django.template import Library
from evap.evaluation.models import Semester

register = Library()


@register.inclusion_tag("navbar.html")
def include_navbar(user, language):
    return {
        'user': user,
        'language': language,
        'result_semesters': Semester.get_all_with_published_courses(),
        'last_five_semesters': Semester.objects.all()[:5],
        'grade_document_semesters': Semester.objects.filter(grade_documents_are_deleted=False),
    }
