from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.utils.translation import get_language
from django.contrib.auth.decorators import login_required

from evap.evaluation.auth import staff_required
from evap.evaluation.models import Semester
from evap.evaluation.tools import calculate_results, calculate_average_grades_and_deviation, TextResult

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
        course.avg_grade, course.avg_deviation = calculate_average_grades_and_deviation(course)

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

    for section in sections:
        results = []
        for result in section.results:
            if isinstance(result, TextResult):
                answers = [answer for answer in result.answers if user_can_see_text_answer(request.user, answer)]
                if answers:
                    results.append(TextResult(question=result.question, answers=answers))
            else:
                results.append(result)
        section.results[:] = results

    # filter empty sections and group by contributor
    course_sections = []
    contributor_sections = OrderedDict()
    for section in sections:
        if not section.results:
            continue
        if section.contributor is None:
            course_sections.append(section)
        else:
            contributor_sections.setdefault(section.contributor, []).append(section)

    # show a warning if course is still in evaluation (for staff preview)
    evaluation_warning = course.state != 'published'

    # results for a course might not be visible because there are not enough answers
    # but it can still be "published" e.g. to show the comment results to lecturers.
    # users who can open the results page see a warning message in this case
    sufficient_votes_warning = not course.can_publish_grades

    show_grades = request.user.is_staff or course.can_publish_grades

    course.avg_grade, course.avg_deviation = calculate_average_grades_and_deviation(course)

    template_data = dict(
            course=course,
            course_sections=course_sections,
            contributor_sections=contributor_sections,
            evaluation_warning=evaluation_warning,
            sufficient_votes_warning=sufficient_votes_warning,
            show_grades=show_grades,
            staff=request.user.is_staff)
    return render(request, "results_course_detail.html", template_data)

def user_can_see_text_answer(user, text_answer):
    if user.is_staff:
        return True
    contributor = text_answer.contribution.contributor
    if text_answer.is_private:
        return contributor == user
    if text_answer.is_published:
        if contributor == user or contributor in user.represented_users.all():
            return True
        if text_answer.contribution.course.is_user_responsible_or_delegate(user):
            return True

    return False
