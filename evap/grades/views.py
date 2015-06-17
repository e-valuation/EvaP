from django.conf import settings
from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Prefetch
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.contrib.auth.decorators import login_required

import os
from sendfile import sendfile

from evap.evaluation.auth import grade_publisher_required, grade_downloader_required
from evap.evaluation.models import Semester, Contribution, Course
from evap.grades.models import GradeDocument
from evap.grades.forms import GradeDocumentForm

def get_graded_courses_with_prefetched_data(semester):
    courses = semester.course_set.filter(is_graded=True).exclude(state='new').prefetch_related(
        Prefetch("contributions", queryset=Contribution.objects.filter(responsible=True).select_related("contributor"), to_attr="responsible_contribution"),
        "degrees")

    course_data = []
    for course in courses:
        course.responsible_contributor = course.responsible_contribution[0].contributor
        course_data.append((course, GradeDocument.objects.filter(course=course, type=GradeDocument.FINAL_GRADES).exists()))

    return course_data


@grade_publisher_required
def index(request):
    template_data = dict(
        semesters=Semester.objects.all()
    )
    return render(request, "grades_index.html", template_data)


@grade_publisher_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    courses = get_graded_courses_with_prefetched_data(semester)

    template_data = dict(
        semester=semester,
        courses=courses,
        disable_if_archived="disabled=disabled" if semester.is_archived else "",
        disable_breadcrumb_semester=True,
    )
    return render(request, "grades_semester_view.html", template_data)


@grade_publisher_required
def course_view(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

    grade_documents = GradeDocument.objects.filter(course=course)

    template_data = dict(
        semester=semester,
        course=course,
        grade_documents=grade_documents,
        disable_if_archived="disabled=disabled" if semester.is_archived else "",
        disable_breadcrumb_course=True,
    )
    return render(request, "grades_course_view.html", template_data)


def helper_grade_upload(request, course, final_grades=False, instance=None):
    if request.method == "POST":
        form = GradeDocumentForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.last_modified_user = request.user
            instance.course = course
            if final_grades:
                instance.type = GradeDocument.FINAL_GRADES
            instance.save()
            return True, form
    else:
        form = GradeDocumentForm(instance=instance)
    return False, form


@grade_publisher_required
def upload_grades(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

    final_grades = request.GET.get('final', 'false') # default: preliminary grades
    final_grades = {'true': True, 'false': False}.get(final_grades.lower()) # convert parameter to boolean

    success, form = helper_grade_upload(request, course, final_grades=final_grades)

    if success:
        messages.success(request, _("Successfully uploaded grades."))
        return redirect('grades:course_view', semester.id, course.id)
    else:
        template_data = dict(
            semester=semester,
            course=course,
            form=form,
            final_grades=final_grades,
        )
        return render(request, "grades_upload_form.html", template_data)


@grade_downloader_required
def download_grades(request, grade_document_id):
    if not request.method == "GET":
        return HttpResponseBadRequest()

    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)

    # final grades can only be downloaded when the course was published
    if not grade_document.course.state == 'published' and grade_document.type == GradeDocument.FINAL_GRADES:
        return HttpResponseForbidden()

    filename = os.path.join(settings.MEDIA_ROOT, grade_document.file.name)
    return sendfile(request, filename, attachment=True, attachment_filename=grade_document.filename())


@grade_publisher_required
def edit_grades(request, semester_id, course_id, grade_document_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)

    success, form = helper_grade_upload(request, course, instance=grade_document)

    if success:
        messages.success(request, _("Successfully updated grades."))
        return redirect('grades:course_view', semester.id, course.id)
    else:
        template_data = dict(
            semester=semester,
            course=course,
            form=form,
            final_grades=False,  # prevent republishing
        )
        return render(request, "grades_upload_form.html", template_data)


@grade_publisher_required
def delete_grades(request, semester_id, course_id, grade_document_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)

    if request.method == 'POST':
        grade_document.delete()
        messages.success(request, _("Successfully deleted grade document."))
        return redirect('grades:course_view', semester_id, course_id)
    else:
        template_data = dict(
            semester=semester,
            course=course,
            grade_document=grade_document,
        )
        return render(request, "grades_delete.html", template_data)
