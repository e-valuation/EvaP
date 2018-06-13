from collections import OrderedDict, namedtuple

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from evap.evaluation.models import Semester, Degree, Contribution
from evap.evaluation.auth import internal_required
from evap.results.tools import calculate_results, calculate_average_distribution, distribution_to_grade, \
    TextAnswer, TextResult, RatingResult, HeadingResult, YesNoResult


@internal_required
def index(request):
    semesters = Semester.get_all_with_published_courses()

    return render(request, "results_index.html", dict(semesters=semesters))


@internal_required
def semester_detail(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    visible_states = ['published']
    if request.user.is_reviewer:
        visible_states += ['in_evaluation', 'evaluated', 'reviewed']

    courses = semester.course_set.filter(state__in=visible_states).prefetch_related("degrees")

    courses = [course for course in courses if course.can_user_see_course(request.user)]

    for course in courses:
        course.distribution = calculate_average_distribution(course)
        course.avg_grade = distribution_to_grade(course.distribution)

    CourseTuple = namedtuple('CourseTuple', ('courses', 'single_results'))

    courses_by_degree = OrderedDict()
    for degree in Degree.objects.all():
        courses_by_degree[degree] = CourseTuple([], [])
    for course in courses:
        if course.is_single_result:
            for degree in course.degrees.all():
                section = calculate_results(course)[0]
                result = section.results[0]
                courses_by_degree[degree].single_results.append((course, result))
        else:
            for degree in course.degrees.all():
                courses_by_degree[degree].courses.append(course)

    template_data = dict(semester=semester, courses_by_degree=courses_by_degree)
    return render(request, "results_semester_detail.html", template_data)


@login_required
def course_detail(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(semester.course_set, id=course_id, semester=semester)

    if not course.can_user_see_results_page(request.user):
        raise PermissionDenied

    sections = calculate_results(course)

    if request.user.is_reviewer:
        public_view = request.GET.get('public_view') != 'false'  # if parameter is not given, show public view.
    else:
        public_view = request.GET.get('public_view') == 'true'  # if parameter is not given, show own view.

    # redirect to non-public view if there is none because the results have not been published
    if not course.can_publish_rating_results:
        public_view = False

    represented_users = list(request.user.represented_users.all())
    represented_users.append(request.user)

    # remove text answers and grades if the user may not see them
    for section in sections:
        results = []
        for result in section.results:
            if isinstance(result, TextResult):
                answers = [answer for answer in result.answers if user_can_see_text_answer(request.user, represented_users, answer, public_view)]
                if answers:
                    results.append(TextResult(question=result.question, answers=answers))
            else:
                results.append(result)

        section.results[:] = results

    # filter empty headings
    for section in sections:
        filtered_results = []
        for index in range(len(section.results)):
            result = section.results[index]
            # filter out if there are no more questions or the next question is also a heading question
            if isinstance(result, HeadingResult):
                if index == len(section.results) - 1 or isinstance(section.results[index + 1], HeadingResult):
                    continue
            filtered_results.append(result)
        section.results[:] = filtered_results

    # remove empty sections
    sections = [section for section in sections if section.results]

    # group by contributor
    course_sections_top = []
    course_sections_bottom = []
    contributor_sections = OrderedDict()
    for section in sections:
        if section.contributor is None:
            if section.questionnaire.is_below_contributors:
                course_sections_bottom.append(section)
            else:
                course_sections_top.append(section)
        else:
            contributor_sections.setdefault(section.contributor,
                                            {'total_votes': 0, 'sections': []})['sections'].append(section)

            for result in section.results:
                if isinstance(result, TextResult):
                    contributor_sections[section.contributor]['total_votes'] += 1
                elif isinstance(result, RatingResult) or isinstance(result, YesNoResult):
                    # Only count rating results if we show the grades.
                    if course.can_publish_rating_results:
                        contributor_sections[section.contributor]['total_votes'] += result.total_count

    course.distribution = calculate_average_distribution(course)
    course.avg_grade = distribution_to_grade(course.distribution)

    template_data = dict(
            course=course,
            course_sections_top=course_sections_top,
            course_sections_bottom=course_sections_bottom,
            contributor_sections=contributor_sections,
            reviewer=request.user.is_reviewer,
            contributor=course.is_user_contributor_or_delegate(request.user),
            can_download_grades=request.user.can_download_grades,
            public_view=public_view)
    return render(request, "results_course_detail.html", template_data)


def user_can_see_text_answer(user, represented_users, text_answer, public_view=False):
    assert text_answer.state in [TextAnswer.PRIVATE, TextAnswer.PUBLISHED]

    if public_view:
        return False
    if user.is_reviewer:
        return True

    contributor = text_answer.contribution.contributor

    if text_answer.is_private:
        return contributor == user

    if text_answer.is_published:
        if text_answer.contribution.responsible:
            return contributor == user or user in contributor.delegates.all()

        if contributor in represented_users:
            return True
        if text_answer.contribution.course.contributions.filter(
                contributor__in=represented_users, comment_visibility=Contribution.ALL_COMMENTS).exists():
            return True
        if text_answer.contribution.is_general and text_answer.contribution.course.contributions.filter(
                contributor__in=represented_users, comment_visibility=Contribution.COURSE_COMMENTS).exists():
            return True

    return False
