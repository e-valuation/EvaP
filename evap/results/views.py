from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.utils.translation import get_language

from evap.evaluation.auth import login_required, fsr_required
from evap.evaluation.models import Semester
from evap.evaluation.tools import calculate_results, calculate_average_grade, TextResult

from evap.results.exporters import ExcelExporter


@login_required
def index(request):
    semesters = Semester.get_all_with_published_courses()

    return render_to_response(
        "results_index.html",
        dict(semesters=semesters),
        context_instance=RequestContext(request))


@login_required
def semester_detail(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = list(semester.course_set.filter(state="published"))

    # annotate each course object with its grade
    for course in courses:
        # first, make sure that there is no preexisting grade attribute
        course.grade = calculate_average_grade(course)

    return render_to_response(
        "results_semester_detail.html",
        dict(
            semester=semester,
            courses=courses
        ),
        context_instance=RequestContext(request))


@fsr_required
def semester_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    filename = "Evaluation-%s-%s.xls" % (semester.name, get_language())

    response = HttpResponse(mimetype="application/vnd.ms-excel")
    response["Content-Disposition"] = "attachment; filename=\"%s\"" % filename

    exporter = ExcelExporter(semester)

    if 'all' in request.GET:
        exporter.export(response, True)
    else:
        exporter.export(response)

    return response


@login_required
def course_detail(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(semester.course_set.filter(state="published"), id=course_id)

    sections = calculate_results(course)

    if (request.user.is_staff != True): # don't remove TextResults for FSR members
    # remove TextResults if user is neither the evaluated person (or a delegate) nor responsible for the course (or a delegate)
        for section in sections:
            if not user_can_see_textresults(request.user, course, section):
                for index, result in list(enumerate(section.results))[::-1]:
                    if isinstance(section.results[index], TextResult):
                        del section.results[index]
    # remove empty sections
        sections = [section for section in sections if section.results]

    return render_to_response(
        "results_course_detail.html",
        dict(
            course=course,
            sections=sections
        ),
        context_instance=RequestContext(request))


def user_can_see_textresults(user, course, section):
    if section.contributor == user:
        return True
    if course.is_user_responsible_or_delegate(user):
        return True

    represented_userprofiles = user.represented_users.all()
    represented_users = [profile.user for profile in represented_userprofiles]
    if section.contributor in represented_users:
        return True

    return False
