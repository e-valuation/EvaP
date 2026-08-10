from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.template import Library

from evap.evaluation.models import Semester, UserProfile

register = Library()


@register.inclusion_tag("navbar.html")
def include_navbar(user: UserProfile | AnonymousUser, language: str):
    semesters_with_unarchived_results_or_grade_documents = Semester.objects.filter(
        Q(results_are_archived=False) | Q(grade_documents_are_deleted=False)
    )

    semesters_with_unarchived_results = [
        semester
        for semester in semesters_with_unarchived_results_or_grade_documents
        if not semester.results_are_archived
    ]
    semesters_with_grade_documents = [
        semester
        for semester in semesters_with_unarchived_results_or_grade_documents
        if not semester.grade_documents_are_deleted
    ]

    return {
        "user": user,
        "current_language": language,
        "languages": settings.LANGUAGES,
        "result_semesters": semesters_with_unarchived_results,
        "grade_document_semesters": semesters_with_grade_documents,
        "debug": settings.DEBUG,
    }
