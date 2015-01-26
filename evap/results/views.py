from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.utils.translation import get_language
from django.contrib.auth.decorators import login_required

from evap.evaluation.auth import staff_required
from evap.evaluation.models import Semester
from evap.evaluation.tools import calculate_results, calculate_average_and_medium_grades, TextResult

from evap.results.exporters import ExcelExporter

from collections import OrderedDict


@login_required
def index(request):
    semesters = Semester.get_all_with_published_courses()

    return render(request, "results_index.html", dict(semesters=semesters))


@login_required
def semester_detail(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = list(semester.course_set.filter(state="published"))

    # annotate each course object with its grades
    for course in courses:
        # first, make sure that there are no preexisting grade attributes
        course.avg_grade, course.med_grade = calculate_average_and_medium_grades(course)

    template_data = dict(semester=semester, courses=courses, staff=request.user.is_staff)
    return render(request, "results_semester_detail.html", template_data)


@staff_required
def semester_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    filename = "Evaluation-%s-%s.xls" % (semester.name, get_language())

    response = HttpResponse(content_type="application/vnd.ms-excel")
    response["Content-Disposition"] = "attachment; filename=\"%s\"" % filename

    ExcelExporter(semester).export(response, 'all' in request.GET)

    return response


@login_required
def course_detail(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(semester.course_set, id=course_id)

    if not course.can_user_see_results(request.user):
        raise PermissionDenied

    sections = calculate_results(course, request.user.is_staff)

    if not request.user.is_staff:
        # remove TextResults if user is neither the evaluated person (or a delegate) nor responsible for the course (or a delegate)
        for section in sections:
            if not user_can_see_textresults(request.user, course, section):
                for i, result in list(enumerate(section.results))[::-1]:
                    if isinstance(result, TextResult):
                        del section.results[i]

    # remove empty sections and group by contributor
    course_sections = []
    contributor_sections = OrderedDict()
    for section in sections:
        if not section.results:
            continue
        if section.contributor is None:
            course_sections.append(section)
        else:
            if section.contributor not in contributor_sections:
                contributor_sections[section.contributor] = []
            contributor_sections[section.contributor].append(section)

    # show a warning if course is still in evaluation (for staff preview)
    evaluation_warning = course.state != 'published'

    # check whether course has a sufficient number of votes for publishing it
    sufficient_votes = course.num_voters >= settings.MIN_ANSWER_COUNT and float(course.num_voters) / course.num_participants >= settings.MIN_ANSWER_PERCENTAGE

    # results for a course might not be visible because there are not enough answers
    # but it can still be "published" e.g. to show the comment results to lecturers.
    # users who can open the results page see a warning message in this case
    sufficient_votes_warning = not sufficient_votes

    course.avg_grade, course.med_grade = calculate_average_and_medium_grades(course)

    template_data = dict(
            course=course,
            course_sections=course_sections,
            contributor_sections=contributor_sections,
            evaluation_warning=evaluation_warning,
            sufficient_votes_warning=sufficient_votes_warning,
            staff=request.user.is_staff)
    return render(request, "results_course_detail.html", template_data)


def user_can_see_textresults(user, course, section):
    if section.contributor == user:
        return True
    if course.is_user_responsible_or_delegate(user):
        return True

    if section.contributor in user.represented_users.all():
        return True

    return False
