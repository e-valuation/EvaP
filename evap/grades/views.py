from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db.models.query import QuerySet
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, TemplateView

from evap.evaluation.auth import (
    grade_downloader_required,
    grade_publisher_or_manager_required,
    grade_publisher_required,
)
from evap.evaluation.models import Course, EmailTemplate, Evaluation, Semester
from evap.evaluation.tools import get_object_from_dict_pk_entry_or_logged_40x
from evap.grades.forms import GradeDocumentForm
from evap.grades.models import GradeDocument
from evap.tools import ilen


@grade_publisher_required
class IndexView(TemplateView):
    template_name = "grades_index.html"

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {
            "semesters": Semester.objects.filter(grade_documents_are_deleted=False),
            "disable_breadcrumb_grades": True,
        }


def course_grade_document_count_tuples(courses: QuerySet[Course]) -> list[tuple[Course, int, int]]:
    courses = courses.prefetch_related("programs", "responsibles", "evaluations", "grade_documents")

    return [
        (
            course,
            ilen(gd for gd in course.grade_documents.all() if gd.type == GradeDocument.Type.MIDTERM_GRADES),
            ilen(gd for gd in course.grade_documents.all() if gd.type == GradeDocument.Type.FINAL_GRADES),
        )
        for course in courses
    ]


@grade_publisher_required
class SemesterView(DetailView):
    template_name = "grades_semester_view.html"
    model = Semester
    pk_url_kwarg = "semester_id"

    object: Semester

    def get_object(self, *args, **kwargs) -> Semester:
        semester = super().get_object(*args, **kwargs)
        if semester.grade_documents_are_deleted:
            raise PermissionDenied
        return semester

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        query = (
            self.object.courses.filter(evaluations__wait_for_grade_upload_before_publishing=True)
            .exclude(evaluations__state=Evaluation.State.NEW)
            .distinct()
        )
        courses = course_grade_document_count_tuples(query)

        return super().get_context_data(**kwargs) | {
            "courses": courses,
            "disable_breadcrumb_semester": True,
        }


@grade_publisher_or_manager_required
class CourseView(DetailView):
    template_name = "grades_course_view.html"
    model = Course
    pk_url_kwarg = "course_id"

    def get_object(self, *args, **kwargs) -> Course:
        course = super().get_object(*args, **kwargs)
        if course.semester.grade_documents_are_deleted:
            raise PermissionDenied
        return course

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {
            "semester": self.object.semester,
            "grade_documents": self.object.grade_documents.all(),
            "disable_breadcrumb_course": True,
        }


def on_grading_process_finished(course):
    evaluations = course.evaluations.all()
    if all(evaluation.state == Evaluation.State.REVIEWED for evaluation in evaluations):
        for evaluation in evaluations:
            assert evaluation.grading_process_is_finished
        for evaluation in evaluations:
            evaluation.publish()
            evaluation.save()

        EmailTemplate.send_participant_publish_notifications(evaluations)
        EmailTemplate.send_contributor_publish_notifications(evaluations)


@grade_publisher_required
def upload_grades(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    semester = course.semester
    if semester.grade_documents_are_deleted:
        raise PermissionDenied

    final_grades = request.GET.get("final") == "true"  # if parameter is not given, assume midterm grades

    grade_document = GradeDocument(course=course)
    if final_grades:
        grade_document.type = GradeDocument.Type.FINAL_GRADES
        grade_document.description_en = settings.DEFAULT_FINAL_GRADES_DESCRIPTION_EN
        grade_document.description_de = settings.DEFAULT_FINAL_GRADES_DESCRIPTION_DE
    else:
        grade_document.type = GradeDocument.Type.MIDTERM_GRADES
        grade_document.description_en = settings.DEFAULT_MIDTERM_GRADES_DESCRIPTION_EN
        grade_document.description_de = settings.DEFAULT_MIDTERM_GRADES_DESCRIPTION_DE

    form = GradeDocumentForm(request.POST or None, request.FILES or None, instance=grade_document)

    if form.is_valid():
        form.save(modifying_user=request.user)

        if final_grades:
            on_grading_process_finished(course)

        messages.success(request, _("Successfully uploaded grades."))
        return redirect("grades:course_view", course.id)

    template_data = {
        "semester": semester,
        "course": course,
        "form": form,
        "final_grades": final_grades,
        "show_automated_publishing_info": final_grades,
    }
    return render(request, "grades_upload_form.html", template_data)


@require_POST
@grade_publisher_required
def set_no_grades(request):
    course = get_object_from_dict_pk_entry_or_logged_40x(Course, request.POST, "course_id")

    try:
        status = bool(int(request.POST["status"]))
    except (KeyError, TypeError, ValueError) as e:
        raise SuspiciousOperation from e

    if course.semester.grade_documents_are_deleted:
        raise PermissionDenied

    course.gets_no_grade_documents = status
    course.save()

    if course.gets_no_grade_documents:
        on_grading_process_finished(course)

    return HttpResponse()  # 200 OK


@require_GET
@grade_downloader_required
def download_grades(request, grade_document_id):
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)
    if grade_document.course.semester.grade_documents_are_deleted:
        raise PermissionDenied

    return FileResponse(grade_document.file.open(), filename=grade_document.filename(), as_attachment=True)


@grade_publisher_required
def edit_grades(request, grade_document_id):
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)
    course = grade_document.course
    semester = course.semester
    if semester.grade_documents_are_deleted:
        raise PermissionDenied

    form = GradeDocumentForm(request.POST or None, request.FILES or None, instance=grade_document)

    final_grades = (
        grade_document.type == GradeDocument.Type.FINAL_GRADES
    )  # if parameter is not given, assume midterm grades

    if form.is_valid():
        form.save(modifying_user=request.user)
        messages.success(request, _("Successfully updated grades."))
        return redirect("grades:course_view", course.id)

    template_data = {
        "semester": semester,
        "course": course,
        "form": form,
        "show_automated_publishing_info": False,
        "final_grades": final_grades,
    }
    return render(request, "grades_upload_form.html", template_data)


@require_POST
@grade_publisher_required
def delete_grades(request):
    grade_document = get_object_from_dict_pk_entry_or_logged_40x(GradeDocument, request.POST, "grade_document_id")
    grade_document.delete()
    return HttpResponse()  # 200 OK
