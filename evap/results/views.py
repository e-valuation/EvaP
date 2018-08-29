from collections import defaultdict
from statistics import median

from django.conf import settings
from django.db.models import QuerySet, Prefetch, Count
from django.core.cache import caches
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template
from django.contrib.auth.decorators import login_required
from django.utils import translation

from evap.evaluation.models import Semester, Degree, Contribution, Course, CourseType
from evap.evaluation.auth import internal_required
from evap.results.tools import collect_results, calculate_average_distribution, distribution_to_grade, \
    TextAnswer, TextResult, HeadingResult, get_single_result_rating_result


def get_course_result_template_fragment_cache_key(course_id, language, can_user_see_results_page):
    return make_template_fragment_key('course_result_template_fragment', [course_id, language, can_user_see_results_page])


def delete_template_cache(course):
    assert course.state != 'published'
    caches['results'].delete(get_course_result_template_fragment_cache_key(course.id, 'en', True))
    caches['results'].delete(get_course_result_template_fragment_cache_key(course.id, 'en', False))
    caches['results'].delete(get_course_result_template_fragment_cache_key(course.id, 'de', True))
    caches['results'].delete(get_course_result_template_fragment_cache_key(course.id, 'de', False))


def warm_up_template_cache(courses):
    courses = get_courses_with_prefetched_data(courses)
    current_language = translation.get_language()
    try:
        for course in courses:
            assert course.state == 'published'
            translation.activate('en')
            get_template('results_index_course.html').render(dict(course=course, can_user_see_results_page=True))
            get_template('results_index_course.html').render(dict(course=course, can_user_see_results_page=False))
            translation.activate('de')
            get_template('results_index_course.html').render(dict(course=course, can_user_see_results_page=True))
            get_template('results_index_course.html').render(dict(course=course, can_user_see_results_page=False))
            assert get_course_result_template_fragment_cache_key(course.id, 'en', True) in caches['results']
            assert get_course_result_template_fragment_cache_key(course.id, 'en', False) in caches['results']
            assert get_course_result_template_fragment_cache_key(course.id, 'de', True) in caches['results']
            assert get_course_result_template_fragment_cache_key(course.id, 'de', False) in caches['results']
    finally:
        translation.activate(current_language)  # reset to previously set language to prevent unwanted side effects


def get_courses_with_prefetched_data(courses):
    if isinstance(courses, QuerySet):
        participant_counts = courses.annotate(num_participants=Count("participants")).values_list("num_participants", flat=True)
        voter_counts = courses.annotate(num_voters=Count("voters")).values_list("num_voters", flat=True)
        courses = (courses
            .select_related("type")
            .prefetch_related(
                "degrees",
                "semester",
                Prefetch("contributions", queryset=Contribution.objects.filter(responsible=True).select_related("contributor"), to_attr="responsible_contributions")
            )
        )
        for course, participant_count, voter_count in zip(courses, participant_counts, voter_counts):
            if course._participant_count is None:
                course.num_participants = participant_count
                course.num_voters = voter_count
            course.responsible_contributors = [contribution.contributor for contribution in course.responsible_contributions]
    for course in courses:
        if not course.is_single_result:
            course.distribution = calculate_average_distribution(course)
            course.avg_grade = distribution_to_grade(course.distribution)
        else:
            course.single_result_rating_result = get_single_result_rating_result(course)
    return courses


@internal_required
def index(request):
    semesters = Semester.get_all_with_published_unarchived_results()
    courses = Course.objects.filter(semester__in=semesters, state='published')
    courses = [course for course in courses if course.can_user_see_course(request.user)]

    if request.user.is_reviewer:
        additional_courses = Course.objects.filter(semester__in=semesters, state__in=['in_evaluation', 'evaluated', 'reviewed'])
        courses += get_courses_with_prefetched_data(additional_courses)

    course_pks = [course.pk for course in courses]
    degrees = Degree.objects.filter(courses__pk__in=course_pks).distinct()
    course_types = CourseType.objects.filter(courses__pk__in=course_pks).distinct()
    template_data = dict(
        courses=courses,
        degrees=degrees,
        course_types=course_types,
        semesters=semesters,
    )
    return render(request, "results_index.html", template_data)


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
        max_answers = max((question_result.count_sum for question_result in questionnaire_result.question_results if question_result.question.is_rating_question), default=0)
        questionnaire_max_answers[questionnaire_result.questionnaire].append(max_answers)

    questionnaire_warning_thresholds = {}
    for questionnaire, max_answers_list in questionnaire_max_answers.items():
        questionnaire_warning_thresholds[questionnaire] = max(settings.RESULTS_WARNING_PERCENTAGE * median(max_answers_list), settings.RESULTS_WARNING_COUNT)

    for questionnaire_result in course_result.questionnaire_results:
        rating_results = [question_result for question_result in questionnaire_result.question_results if question_result.question.is_rating_question]
        max_answers = max((rating_result.count_sum for rating_result in rating_results), default=0)
        questionnaire_result.warning = 0 < max_answers < questionnaire_warning_thresholds[questionnaire_result.questionnaire]

        for rating_result in rating_results:
            rating_result.warning = questionnaire_result.warning or rating_result.has_answers and rating_result.count_sum < questionnaire_warning_thresholds[questionnaire_result.questionnaire]


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
