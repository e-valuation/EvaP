from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.utils.translation import get_language

from evap.evaluation.auth import login_required, fsr_required
from evap.evaluation.models import Semester
from evap.evaluation.tools import calculate_results, calculate_average_and_medium_grades, TextResult

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

    # annotate each course object with its grades
    for course in courses:
        # first, make sure that there are no preexisting grade attributes
        course.avg_grade, course.med_grade = calculate_average_and_medium_grades(course)

    return render_to_response(
        "results_semester_detail.html",
        dict(
            semester=semester,
            courses=courses,
            staff=request.user.is_staff
        ),
        context_instance=RequestContext(request))


@fsr_required
def semester_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    filename = "Evaluation-%s-%s.xls" % (semester.name, get_language())

    response = HttpResponse(mimetype="application/vnd.ms-excel")
    response["Content-Disposition"] = "attachment; filename=\"%s\"" % filename

    ExcelExporter(semester).export(response, 'all' in request.GET)

    return response


@login_required
def course_detail(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    
    # staff can see preview of results even when course is not published
    if request.user.is_staff:
        course = get_object_or_404(semester.course_set.filter(state__in=['inEvaluation', 'evaluated', 'reviewed', 'published']), id=course_id)
    # everyone else can only see published results
    else:
        course = get_object_or_404(semester.course_set.filter(state="published"), id=course_id)

    sections = calculate_results(course, request.user.is_staff)

    if not request.user.is_staff:
        # remove TextResults if user is neither the evaluated person (or a delegate) nor responsible for the course (or a delegate)
        for section in sections:
            if not user_can_see_textresults(request.user, course, section):
                for index, result in list(enumerate(section.results))[::-1]:
                    if isinstance(result, TextResult):
                        del section.results[index]

    # remove empty sections and group by contributor
    course_sections = []
    contributor_sections = {}
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
    # but it can still be "published" e.g. to show the comment results to lecturers
    # the FSR can still see all results but gets a warning message
    sufficient_votes_warning = (not sufficient_votes) and request.user.is_staff

    course.avg_grade, course.med_grade = calculate_average_and_medium_grades(course)

    return render_to_response(
        "results_course_detail.html",
        dict(
            course=course,
            course_sections=course_sections,
            contributor_sections=contributor_sections,
            evaluation_warning=evaluation_warning,
            sufficient_votes_warning=sufficient_votes_warning,
            staff=request.user.is_staff
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
