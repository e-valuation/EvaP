from collections import OrderedDict, namedtuple, defaultdict
from statistics import median

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from evap.evaluation.models import Semester, Degree, Contribution
from evap.evaluation.auth import internal_required
from evap.results.tools import collect_results, calculate_average_distribution, distribution_to_grade, \
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
                question_result = collect_results(course).questionnaire_results[0].question_results[0]
                courses_by_degree[degree].single_results.append((course, question_result))
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

    course_result = collect_results(course)

    if request.user.is_reviewer:
        public_view = request.GET.get('public_view') != 'false'  # if parameter is not given, show public view.
    else:
        public_view = request.GET.get('public_view') == 'true'  # if parameter is not given, show own view.

    # redirect to non-public view if there is none because the results have not been published
    if not course.can_publish_rating_results:
        public_view = False

    represented_users = list(request.user.represented_users.all()) + [request.user]

    # remove text answers if the user may not see them
    for questionnaire_result in course_result.questionnaire_results:
        for question_result in questionnaire_result.question_results:
            if isinstance(question_result, TextResult):
                question_result.answers = [answer for answer in question_result.answers if user_can_see_text_answer(request.user, represented_users, answer, public_view)]
        # remove empty TextResults
        questionnaire_result.question_results = [result for result in questionnaire_result.question_results if not isinstance(result, TextResult) or len(result.answers) > 0]

    # filter empty headings
    for questionnaire_result in course_result.questionnaire_results:
        filtered_question_results = []
        for index, question_result in enumerate(questionnaire_result.question_results):
            # filter out if there are no more questions or the next question is also a heading question
            if isinstance(question_result, HeadingResult):
                if index == len(questionnaire_result.question_results) - 1 or isinstance(questionnaire_result.question_results[index + 1], HeadingResult):
                    continue
            filtered_question_results.append(question_result)
        questionnaire_result.question_results = filtered_question_results

    # remove empty questionnaire_results and contribution_results
    for contribution_result in course_result.contribution_results:
        contribution_result.questionnaire_results = [questionnaire_result for questionnaire_result in contribution_result.questionnaire_results if questionnaire_result.question_results]
    course_result.contribution_results = [contribution_result for contribution_result in course_result.contribution_results if contribution_result.questionnaire_results]

    add_warnings(course, course_result)

    # split course_result into different lists
    course_questionnaire_results_top = []
    course_questionnaire_results_bottom = []
    contributor_contribution_results = []
    for contribution_result in course_result.contribution_results:
        if contribution_result.contributor is None:
            for questionnaire_result in contribution_result.questionnaire_results:
                if questionnaire_result.questionnaire.is_below_contributors:
                    course_questionnaire_results_bottom.append(questionnaire_result)
                else:
                    course_questionnaire_results_top.append(questionnaire_result)
        else:
            contributor_contribution_results.append(contribution_result)

    if not contributor_contribution_results:
        course_questionnaire_results_top += course_questionnaire_results_bottom
        course_questionnaire_results_bottom = []

    course.distribution = calculate_average_distribution(course)
    course.avg_grade = distribution_to_grade(course.distribution)

    template_data = dict(
            course=course,
            course_questionnaire_results_top=course_questionnaire_results_top,
            course_questionnaire_results_bottom=course_questionnaire_results_bottom,
            contributor_contribution_results=contributor_contribution_results,
            reviewer=request.user.is_reviewer,
            contributor=course.is_user_contributor_or_delegate(request.user),
            can_download_grades=request.user.can_download_grades,
            public_view=public_view)
    return render(request, "results_course_detail.html", template_data)


def add_warnings(course, course_result):
    if not course.can_publish_rating_results:
        return

    # calculate the median values of how many people answered a questionnaire across all contributions
    questionnaire_max_answers = defaultdict(list)
    for questionnaire_result in course_result.questionnaire_results:
        max_answers = max((question_result.total_count for question_result in questionnaire_result.question_results if question_result.question.is_rating_question), default=0)
        questionnaire_max_answers[questionnaire_result.questionnaire].append(max_answers)

    questionnaire_warning_thresholds = {}
    for questionnaire, max_answers_list in questionnaire_max_answers.items():
        questionnaire_warning_thresholds[questionnaire] = max(settings.RESULTS_WARNING_PERCENTAGE * median(max_answers_list), settings.RESULTS_WARNING_COUNT)

    for questionnaire_result in course_result.questionnaire_results:
        rating_results = [question_result for question_result in questionnaire_result.question_results if question_result.question.is_rating_question]
        max_answers = max((rating_result.total_count for rating_result in rating_results), default=0)
        questionnaire_result.warning = 0 < max_answers < questionnaire_warning_thresholds[questionnaire_result.questionnaire]

        for rating_result in rating_results:
            rating_result.warning = questionnaire_result.warning or rating_result.has_answers and rating_result.total_count < questionnaire_warning_thresholds[questionnaire_result.questionnaire]


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
