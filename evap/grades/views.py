from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Prefetch
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.http import HttpResponseBadRequest, HttpResponseForbidden

from sendfile import sendfile

from evap.evaluation.auth import grade_publisher_required, grade_downloader_required
from evap.evaluation.models import Semester, Contribution, Course
from evap.grades.models import GradeDocument
from evap.grades.forms import GradeDocumentForm
from evap.evaluation.tools import send_publish_notifications


@grade_publisher_required
def index(request):
    template_data = dict(
        semesters=Semester.objects.all()
    )
    return render(request, "grades_index.html", template_data)


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

    template_data = dict(
        semester=semester,
        course=course,
        grade_documents=course.grade_documents.all(),
        disable_if_archived="disabled=disabled" if semester.is_archived else "",
        disable_breadcrumb_course=True,
    )
    return render(request, "grades_course_view.html", template_data)


@grade_publisher_required
def upload_grades(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

    final_grades = request.GET.get('final', 'false') # default: midterm grades
    final_grades = {'true': True, 'false': False}.get(final_grades.lower()) # convert parameter to boolean

    form = GradeDocumentForm(request.POST or None, request.FILES or None, course=course, final_grades=final_grades, user=request.user)

    if form.is_valid():
        form.save()
        if final_grades and course.state == 'reviewed':
            course.publish()
            course.save()
            send_publish_notifications(grade_document_courses=[course], evaluation_results_courses=[course])
        else:
            send_publish_notifications(grade_document_courses=[course])            

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


@grade_downloader_required
def download_grades(request, grade_document_id):
    if not request.method == "GET":
        return HttpResponseBadRequest()

    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)
    return sendfile(request, grade_document.file.path, attachment=True, attachment_filename=grade_document.filename())


@grade_publisher_required
def edit_grades(request, semester_id, course_id, grade_document_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)
    final_grades = grade_document.type == GradeDocument.FINAL_GRADES

    form = GradeDocumentForm(request.POST or None, request.FILES or None, course=course, final_grades=final_grades, instance=grade_document, user=request.user)

    if form.is_valid():
        form.save()
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
