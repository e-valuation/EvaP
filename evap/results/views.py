from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.utils.translation import get_language
from django.contrib.auth.decorators import login_required

from evap.evaluation.auth import staff_required
from evap.evaluation.models import Semester
from evap.evaluation.tools import calculate_results, calculate_average_and_medium_grades, TextResult, ResultSection, replace_results

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

    sections = calculate_results(course)

    cleaned_sections = []
    if request.user.is_staff:
        cleaned_sections = sections
    else:
        for section in sections:
            results = []
            for result in section.results:
                if isinstance(result, TextResult):
                    answers = [answer for answer in result.answers if user_can_see_text_answer(request.user, course, answer)]
                    if answers:
                        results.append(TextResult(question=result.question, answers=answers))
                else:
                    results.append(result)
            if results:
                cleaned_sections.append(replace_results(section, results))

    # remove empty sections and group by contributor
    course_sections = []
    contributor_sections = OrderedDict()
    for section in cleaned_sections:
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

    show_grades = request.user.is_staff or course.can_publish_grades

    course.avg_grade, course.med_grade = calculate_average_and_medium_grades(course)

    template_data = dict(
            course=course,
            course_sections=course_sections,
            contributor_sections=contributor_sections,
            evaluation_warning=evaluation_warning,
            sufficient_votes_warning=sufficient_votes_warning,
            show_grades=show_grades,
            staff=request.user.is_staff)
    return render(request, "results_course_detail.html", template_data)

def user_can_see_text_answer(user, course, text_answer):
    contributor = text_answer.contribution.contributor
    if contributor == user:
        return True
    if text_answer.published:
        if course.is_user_responsible_or_delegate(user):
            return True
        if contributor in user.represented_users.all():
            return True

    return False
