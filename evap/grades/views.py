from django.shortcuts import get_object_or_404, render, redirect
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.conf import settings
from django.utils.translation import ugettext as _
from django.http import HttpResponse
from django.views.decorators.http import require_POST, require_GET

from sendfile import sendfile

from evap.evaluation.auth import grade_publisher_required, grade_downloader_required, grade_publisher_or_manager_required
from evap.evaluation.models import Course, Semester, EmailTemplate
from evap.grades.models import GradeDocument
from evap.grades.forms import GradeDocumentForm


@grade_publisher_required
def index(request):
    template_data = dict(
        semesters=Semester.objects.filter(grade_documents_are_deleted=False),
        disable_breadcrumb_grades=True,
    )
    return render(request, "grades_index.html", template_data)


def prefetch_data(courses):
    courses = courses.prefetch_related("degrees", "responsibles")

    course_data = []
    for course in courses:
        course_data.append((
            course,
            course.midterm_grade_documents.count(),
            course.final_grade_documents.count()
        ))

    return course_data


@grade_publisher_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.grade_documents_are_deleted:
        raise PermissionDenied

    courses = semester.courses.filter(is_graded=True).exclude(evaluations__state='new')
    courses = prefetch_data(courses)

    template_data = dict(
        semester=semester,
        courses=courses,
        disable_if_archived="disabled" if semester.grade_documents_are_deleted else "",
        disable_breadcrumb_semester=True,
    )
    return render(request, "grades_semester_view.html", template_data)


@grade_publisher_or_manager_required
def course_view(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.grade_documents_are_deleted:
        raise PermissionDenied
    course = get_object_or_404(Course, id=course_id, semester=semester)

    template_data = dict(
        semester=semester,
        course=course,
        grade_documents=course.grade_documents.all(),
        disable_if_archived="disabled" if semester.grade_documents_are_deleted else "",
        disable_breadcrumb_course=True,
    )
    return render(request, "grades_course_view.html", template_data)


@grade_publisher_required
def upload_grades(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.grade_documents_are_deleted:
        raise PermissionDenied
    course = get_object_or_404(Course, id=course_id, semester=semester)

    final_grades = request.GET.get('final') == 'true'  # if parameter is not given, assume midterm grades

    grade_document = GradeDocument(course=course)
    if final_grades:
        grade_document.type = GradeDocument.FINAL_GRADES
        grade_document.description_en = settings.DEFAULT_FINAL_GRADES_DESCRIPTION_EN
        grade_document.description_de = settings.DEFAULT_FINAL_GRADES_DESCRIPTION_DE
    else:
        grade_document.type = GradeDocument.MIDTERM_GRADES
        grade_document.description_en = settings.DEFAULT_MIDTERM_GRADES_DESCRIPTION_EN
        grade_document.description_de = settings.DEFAULT_MIDTERM_GRADES_DESCRIPTION_DE

    form = GradeDocumentForm(request.POST or None, request.FILES or None, instance=grade_document)

    if form.is_valid():
        form.save(modifying_user=request.user)
        evaluations = course.evaluations.all()
        if final_grades and all(evaluation.state == 'reviewed' for evaluation in evaluations):
            for evaluation in evaluations:
                evaluation.publish()
                evaluation.save()

            EmailTemplate.send_participant_publish_notifications(evaluations)
            EmailTemplate.send_contributor_publish_notifications(evaluations)

        messages.success(request, _("Successfully uploaded grades."))
        return redirect('grades:course_view', semester.id, course.id)

    template_data = dict(
        semester=semester,
        course=course,
        form=form,
        final_grades=final_grades,
        show_automated_publishing_info=final_grades,
    )
    return render(request, "grades_upload_form.html", template_data)


@require_POST
@grade_publisher_required
def toggle_no_grades(request):
    course_id = request.POST.get("course_id")
    course = get_object_or_404(Course, id=course_id)
    if course.semester.grade_documents_are_deleted:
        raise PermissionDenied

    course.gets_no_grade_documents = not course.gets_no_grade_documents
    course.save()
    evaluations = course.evaluations.all()
    if course.gets_no_grade_documents and all(evaluation.state == 'reviewed' for evaluation in evaluations):
        for evaluation in evaluations:
            evaluation.publish()
            evaluation.save()

        EmailTemplate.send_participant_publish_notifications(evaluations)
        EmailTemplate.send_contributor_publish_notifications(evaluations)

    return HttpResponse()  # 200 OK


@require_GET
@grade_downloader_required
def download_grades(request, grade_document_id):
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)
    if grade_document.course.semester.grade_documents_are_deleted:
        raise PermissionDenied

    return sendfile(request, grade_document.file.path, attachment=True, attachment_filename=grade_document.filename())


@grade_publisher_required
def edit_grades(request, semester_id, course_id, grade_document_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.grade_documents_are_deleted:
        raise PermissionDenied
    course = get_object_or_404(Course, id=course_id, semester=semester)
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id, course=course)

    form = GradeDocumentForm(request.POST or None, request.FILES or None, instance=grade_document)

    if form.is_valid():
        form.save(modifying_user=request.user)
        messages.success(request, _("Successfully updated grades."))
        return redirect('grades:course_view', semester.id, course.id)

    template_data = dict(
        semester=semester,
        course=course,
        form=form,
        show_automated_publishing_info=False,
    )
    return render(request, "grades_upload_form.html", template_data)


@require_POST
@grade_publisher_required
def delete_grades(request):
    grade_document_id = request.POST.get("grade_document_id")
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)

    grade_document.delete()
    return HttpResponse()  # 200 OK
