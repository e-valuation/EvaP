from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Prefetch
from django.contrib import messages
from django.conf import settings
from django.utils.translation import ugettext as _
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST, require_GET

from sendfile import sendfile

from evap.evaluation.auth import grade_publisher_required, grade_downloader_required, grade_publisher_or_staff_required, staff_required
from evap.evaluation.models import Semester, Contribution, Course, EmailTemplate
from evap.grades.models import GradeDocument, SemesterGradeDownloadActivation
from evap.grades.forms import GradeDocumentForm
from evap.evaluation.tools import send_publish_notifications

from evap.staff.views import semester_view as staff_semester_view


@grade_publisher_required
def index(request):
    template_data = dict(
        semesters=Semester.objects.all()
    )
    return render(request, "grades_index.html", template_data)


def prefetch_data(courses):
    courses = courses.prefetch_related(
        Prefetch("contributions", queryset=Contribution.objects.filter(responsible=True).select_related("contributor"), to_attr="responsible_contribution"),
        "degrees")

    course_data = []
    for course in courses:
        course.responsible_contributor = course.responsible_contribution[0].contributor
        course_data.append((
            course,
            course.midterm_grade_documents.count(),
            course.final_grade_documents.count()
        ))

    return course_data


@grade_publisher_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    courses = semester.course_set.filter(is_graded=True).exclude(state='new')
    courses = prefetch_data(courses)

    template_data = dict(
        semester=semester,
        courses=courses,
        disable_if_archived="disabled=disabled" if semester.is_archived else "",
        disable_breadcrumb_semester=True,
    )
    return render(request, "grades_semester_view.html", template_data)


@grade_publisher_or_staff_required
def course_view(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)
    is_grade_publisher = request.user.is_grade_publisher

    template_data = dict(
        semester=semester,
        course=course,
        grade_documents=course.grade_documents.all(),
        disable_if_archived="disabled=disabled" if semester.is_archived else "",
        disable_breadcrumb_course=True,
        is_grade_publisher=is_grade_publisher,
    )
    return render(request, "grades_course_view.html", template_data)


@grade_publisher_required
def upload_grades(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
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
        if final_grades and course.state == 'reviewed':
            course.publish()
            course.save()
            send_publish_notifications([course])

        messages.success(request, _("Successfully uploaded grades."))
        return redirect('grades:course_view', semester.id, course.id)
    else:
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

    course.gets_no_grade_documents = not course.gets_no_grade_documents
    course.save()
    if course.gets_no_grade_documents:
        if course.state == 'reviewed':
            course.publish()
            course.save()
            send_publish_notifications([course])

    return HttpResponse()  # 200 OK


@require_GET
@grade_downloader_required
def download_grades(request, grade_document_id):
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)
    if not grade_document.course.grades_activated:
        return HttpResponseForbidden()

    return sendfile(request, grade_document.file.path, attachment=True, attachment_filename=grade_document.filename())


@grade_publisher_required
def edit_grades(request, semester_id, course_id, grade_document_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id, course=course)

    form = GradeDocumentForm(request.POST or None, request.FILES or None, instance=grade_document)

    if form.is_valid():
        form.save(modifying_user=request.user)
        messages.success(request, _("Successfully updated grades."))
        return redirect('grades:course_view', semester.id, course.id)
    else:
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


@staff_required
def semester_grade_activation(request, semester_id, active):
    semester = get_object_or_404(Semester, id=semester_id)
    active = active == 'on'

    SemesterGradeDownloadActivation.objects.update_or_create(
        semester=semester,
        defaults={'is_active': active})

    return staff_semester_view(request=request, semester_id=semester_id)
