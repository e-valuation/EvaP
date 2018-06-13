from collections import OrderedDict, namedtuple, defaultdict
from statistics import median

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from evap.evaluation.models import Semester, Degree, Contribution
from evap.evaluation.auth import internal_required
from evap.results.tools import calculate_results, calculate_average_distribution, distribution_to_grade, \
    TextAnswer, TextResult, HeadingResult


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

    represented_users = list(request.user.represented_users.all()) + [request.user]

    # remove text answers if the user may not see them
    for section in sections:
        for result in section.results:
            if isinstance(result, TextResult):
                result.answers = [answer for answer in result.answers if user_can_see_text_answer(request.user, represented_users, answer, public_view)]
        # remove empty TextResults
        section.results = [result for result in section.results if not isinstance(result, TextResult) or len(result.answers) > 0]

    # filter empty headings
    for section in sections:
        filtered_results = []
        for index, result in enumerate(section.results):
            # filter out if there are no more questions or the next question is also a heading question
            if isinstance(result, HeadingResult):
                if index == len(section.results) - 1 or isinstance(section.results[index + 1], HeadingResult):
                    continue
            filtered_results.append(result)
        section.results = filtered_results

    # remove empty sections
    sections = [section for section in sections if section.results]

    add_warnings(course, sections)

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
                                            {'has_votes': False, 'sections': []})['sections'].append(section)

            if any(result.question.is_rating_question and result.total_count or result.question.is_text_question for result in section.results):
                contributor_sections[section.contributor]['has_votes'] = True

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


def add_warnings(course, result_sections):
    if not course.can_publish_rating_results:
        return

    # calculate the median values of how many people answered a questionnaire across all contributions
    questionnaire_max_answers = defaultdict(list)
    for section in result_sections:
        max_answers = max((result.total_count for result in section.results if result.question.is_rating_question), default=0)
        questionnaire_max_answers[section.questionnaire].append(max_answers)

    questionnaire_warning_thresholds = {}
    for questionnaire, max_answers_list in questionnaire_max_answers.items():
        questionnaire_warning_thresholds[questionnaire] = max(settings.RESULTS_WARNING_PERCENTAGE * median(max_answers_list), settings.RESULTS_WARNING_COUNT)

    for section in result_sections:
        rating_results = [result for result in section.results if result.question.is_rating_question]
        max_answers = max((result.total_count for result in rating_results), default=0)
        section.warning = 0 < max_answers < questionnaire_warning_thresholds[section.questionnaire]

        for result in rating_results:
            result.warning = section.warning or result.has_answers and result.total_count < questionnaire_warning_thresholds[section.questionnaire]


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
