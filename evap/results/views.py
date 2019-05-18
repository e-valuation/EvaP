from collections import defaultdict
from statistics import median

from django.conf import settings
from django.db.models import Count, QuerySet
from django.core.cache import caches
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template
from django.contrib.auth.decorators import login_required
from django.utils import translation

from evap.evaluation.models import Semester, Degree, Evaluation, CourseType, UserProfile
from evap.evaluation.auth import internal_required
from evap.results.tools import (collect_results, calculate_average_distribution, distribution_to_grade,
                                get_evaluations_with_course_result_attributes, get_single_result_rating_result,
                                HeadingResult, TextResult, can_textanswer_be_seen_by)


def get_course_result_template_fragment_cache_key(course_id, language):
    return make_template_fragment_key('course_result_template_fragment', [course_id, language])


def get_evaluation_result_template_fragment_cache_key(evaluation_id, language, links_to_results_page):
    return make_template_fragment_key('evaluation_result_template_fragment', [evaluation_id, language, links_to_results_page])


def delete_template_cache(evaluation):
    assert evaluation.state != 'published'
    _delete_template_cache_impl(evaluation)


def _delete_template_cache_impl(evaluation):
    _delete_evaluation_template_cache_impl(evaluation)
    _delete_course_template_cache_impl(evaluation.course)


def _delete_evaluation_template_cache_impl(evaluation):
    caches['results'].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, 'en', True))
    caches['results'].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, 'en', False))
    caches['results'].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, 'de', True))
    caches['results'].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, 'de', False))


def _delete_course_template_cache_impl(course):
    caches['results'].delete(get_course_result_template_fragment_cache_key(course.id, 'en'))
    caches['results'].delete(get_course_result_template_fragment_cache_key(course.id, 'de'))


def warm_up_template_cache(evaluations):
    evaluations = get_evaluations_with_course_result_attributes(get_evaluations_with_prefetched_data(evaluations))
    current_language = translation.get_language()
    courses_to_render = set([evaluation.course for evaluation in evaluations if evaluation.course.evaluation_count > 1])
    try:
        for course in courses_to_render:
            translation.activate('en')
            get_template('results_index_course.html').render(dict(course=course))
            translation.activate('de')
            get_template('results_index_course.html').render(dict(course=course))
            assert get_course_result_template_fragment_cache_key(course.id, 'en') in caches['results']
            assert get_course_result_template_fragment_cache_key(course.id, 'de') in caches['results']
        for evaluation in evaluations:
            assert evaluation.state == 'published'
            is_subentry = evaluation.course.evaluation_count > 1
            translation.activate('en')
            get_template('results_index_evaluation.html').render(dict(evaluation=evaluation, links_to_results_page=True, is_subentry=is_subentry))
            get_template('results_index_evaluation.html').render(dict(evaluation=evaluation, links_to_results_page=False, is_subentry=is_subentry))
            translation.activate('de')
            get_template('results_index_evaluation.html').render(dict(evaluation=evaluation, links_to_results_page=True, is_subentry=is_subentry))
            get_template('results_index_evaluation.html').render(dict(evaluation=evaluation, links_to_results_page=False, is_subentry=is_subentry))
            assert get_evaluation_result_template_fragment_cache_key(evaluation.id, 'en', True) in caches['results']
            assert get_evaluation_result_template_fragment_cache_key(evaluation.id, 'en', False) in caches['results']
            assert get_evaluation_result_template_fragment_cache_key(evaluation.id, 'de', True) in caches['results']
            assert get_evaluation_result_template_fragment_cache_key(evaluation.id, 'de', False) in caches['results']
    finally:
        translation.activate(current_language)  # reset to previously set language to prevent unwanted side effects


def update_template_cache(evaluations):
    for evaluation in evaluations:
        assert evaluation.state == "published"
        _delete_template_cache_impl(evaluation)
        warm_up_template_cache([evaluation])


def update_template_cache_of_published_evaluations_in_course(course):
    course_evaluations = course.evaluations.filter(state="published")
    for course_evaluation in course_evaluations:
        _delete_evaluation_template_cache_impl(course_evaluation)
    _delete_course_template_cache_impl(course)
    warm_up_template_cache(course_evaluations)


def get_evaluations_with_prefetched_data(evaluations):
    if isinstance(evaluations, QuerySet):
        participant_counts = evaluations.annotate(num_participants=Count("participants")).values_list("num_participants", flat=True)
        voter_counts = evaluations.annotate(num_voters=Count("voters")).values_list("num_voters", flat=True)
        course_evaluations_counts = evaluations.annotate(num_course_evaluations=Count("course__evaluations")).values_list("num_course_evaluations", flat=True)
        evaluations = (evaluations
            .select_related("course__type")
            .prefetch_related(
                "course__degrees",
                "course__semester",
                "course__responsibles",
            )
        )
        for evaluation, participant_count, voter_count, course_evaluations_count in zip(evaluations, participant_counts, voter_counts, course_evaluations_counts):
            if evaluation._participant_count is None:
                evaluation.num_participants = participant_count
                evaluation.num_voters = voter_count
            evaluation.course_evaluations_count = course_evaluations_count
    for evaluation in evaluations:
        if not evaluation.is_single_result:
            evaluation.distribution = calculate_average_distribution(evaluation)
            evaluation.avg_grade = distribution_to_grade(evaluation.distribution)
        else:
            evaluation.single_result_rating_result = get_single_result_rating_result(evaluation)
    return evaluations


@internal_required
def index(request):
    semesters = Semester.get_all_with_published_unarchived_results()
    evaluations = Evaluation.objects.filter(course__semester__in=semesters, state='published')
    evaluations = [evaluation for evaluation in evaluations if evaluation.can_be_seen_by(request.user)]

    if request.user.is_reviewer:
        additional_evaluations = get_evaluations_with_prefetched_data(
            Evaluation.objects.filter(
                course__semester__in=semesters,
                state__in=['in_evaluation', 'evaluated', 'reviewed']
            )
        )
        additional_evaluations = get_evaluations_with_course_result_attributes(additional_evaluations)
        evaluations += additional_evaluations

    evaluations.sort(key=lambda evaluation: (evaluation.course.semester.pk, evaluation.full_name))  # evaluations must be sorted for regrouping them in the template

    evaluation_pks = [evaluation.pk for evaluation in evaluations]
    degrees = Degree.objects.filter(courses__evaluations__pk__in=evaluation_pks).distinct()
    course_types = CourseType.objects.filter(courses__evaluations__pk__in=evaluation_pks).distinct()
    template_data = dict(
        evaluations=evaluations,
        degrees=degrees,
        course_types=course_types,
        semesters=semesters,
    )
    return render(request, "results_index.html", template_data)


@login_required
def evaluation_detail(request, semester_id, evaluation_id):
    semester = get_object_or_404(Semester, id=semester_id)
    evaluation = get_object_or_404(semester.evaluations, id=evaluation_id, course__semester=semester)

    if not evaluation.can_results_page_be_seen_by(request.user):
        raise PermissionDenied

    evaluation_result = collect_results(evaluation)

    if request.user.is_reviewer:
        view = request.GET.get('view', 'public')  # if parameter is not given, show public view.
    else:
        view = request.GET.get('view', 'full')  # if parameter is not given, show own view.
    if view not in ['public', 'full', 'export']:
        view = 'public'

    view_as_user = request.user
    if view == 'export' and request.user.is_staff:
        view_as_user = UserProfile.objects.get(id=int(request.GET.get('contributor_id', request.user.id)))

    represented_users = [view_as_user]
    if view != 'export':
        represented_users += list(view_as_user.represented_users.all())
    # redirect to non-public view if there is none because the results have not been published
    if not evaluation.can_publish_rating_results and view == 'public':
        view = 'full'

    # remove text answers if the user may not see them
    for questionnaire_result in evaluation_result.questionnaire_results:
        for question_result in questionnaire_result.question_results:
            if isinstance(question_result, TextResult):
                question_result.answers = [answer for answer in question_result.answers if can_textanswer_be_seen_by(view_as_user, represented_users, answer, view)]
        # remove empty TextResults
        questionnaire_result.question_results = [result for result in questionnaire_result.question_results if not isinstance(result, TextResult) or len(result.answers) > 0]

    # filter empty headings
    for questionnaire_result in evaluation_result.questionnaire_results:
        filtered_question_results = []
        for index, question_result in enumerate(questionnaire_result.question_results):
            # filter out if there are no more questions or the next question is also a heading question
            if isinstance(question_result, HeadingResult):
                if index == len(questionnaire_result.question_results) - 1 or isinstance(questionnaire_result.question_results[index + 1], HeadingResult):
                    continue
            filtered_question_results.append(question_result)
        questionnaire_result.question_results = filtered_question_results

    # remove empty questionnaire_results and contribution_results
    for contribution_result in evaluation_result.contribution_results:
        contribution_result.questionnaire_results = [questionnaire_result for questionnaire_result in contribution_result.questionnaire_results if questionnaire_result.question_results]
    evaluation_result.contribution_results = [contribution_result for contribution_result in evaluation_result.contribution_results if contribution_result.questionnaire_results]

    add_warnings(evaluation, evaluation_result)

    # split evaluation_result into different lists
    general_questionnaire_results_top = []
    general_questionnaire_results_bottom = []
    contributor_contribution_results = []
    for contribution_result in evaluation_result.contribution_results:
        if contribution_result.contributor is None:
            for questionnaire_result in contribution_result.questionnaire_results:
                if questionnaire_result.questionnaire.is_below_contributors:
                    general_questionnaire_results_bottom.append(questionnaire_result)
                else:
                    general_questionnaire_results_top.append(questionnaire_result)
        elif view != 'export' or view_as_user.id == contribution_result.contributor.id:
            contributor_contribution_results.append(contribution_result)

    if not contributor_contribution_results:
        general_questionnaire_results_top += general_questionnaire_results_bottom
        general_questionnaire_results_bottom = []

    course_evaluations = []
    if evaluation.course.evaluations.count() > 1:
        course_evaluations = [evaluation for evaluation in evaluation.course.evaluations.filter(state="published") if evaluation.can_be_seen_by(request.user)]
        if request.user.is_reviewer:
            course_evaluations += evaluation.course.evaluations.filter(state__in=['in_evaluation', 'evaluated', 'reviewed'])
        course_evaluations = get_evaluations_with_course_result_attributes(course_evaluations)
        for course_evaluation in course_evaluations:
            if course_evaluation.is_single_result:
                course_evaluation.single_result_rating_result = get_single_result_rating_result(course_evaluation)
            else:
                course_evaluation.distribution = calculate_average_distribution(course_evaluation)
                course_evaluation.avg_grade = distribution_to_grade(course_evaluation.distribution)

    other_contributors = []
    if view == 'export':
        other_contributors = [contribution_result.contributor for contribution_result in evaluation_result.contribution_results if contribution_result.contributor not in [None, view_as_user]]

    # if the evaluation is not published, the rendered results are not cached, so we need to attach distribution
    # information for rendering the distribution bar
    if evaluation.state != 'published':
        evaluation = get_evaluations_with_prefetched_data([evaluation])[0]

    template_data = dict(
        evaluation=evaluation,
        course=evaluation.course,
        course_evaluations=course_evaluations,
        general_questionnaire_results_top=general_questionnaire_results_top,
        general_questionnaire_results_bottom=general_questionnaire_results_bottom,
        contributor_contribution_results=contributor_contribution_results,
        is_reviewer=view_as_user.is_reviewer,
        is_contributor=evaluation.is_user_contributor(view_as_user),
        is_responsible_or_contributor_or_delegate=evaluation.is_user_responsible_or_contributor_or_delegate(view_as_user),
        can_download_grades=view_as_user.can_download_grades,
        view=view,
        view_as_user=view_as_user,
        other_contributors=other_contributors,
    )
    return render(request, "results_evaluation_detail.html", template_data)


def add_warnings(evaluation, evaluation_result):
    if not evaluation.can_publish_rating_results:
        return

    # calculate the median values of how many people answered a questionnaire across all contributions
    questionnaire_max_answers = defaultdict(list)
    for questionnaire_result in evaluation_result.questionnaire_results:
        max_answers = max((question_result.count_sum for question_result in questionnaire_result.question_results if question_result.question.is_rating_question), default=0)
        questionnaire_max_answers[questionnaire_result.questionnaire].append(max_answers)

    questionnaire_warning_thresholds = {}
    for questionnaire, max_answers_list in questionnaire_max_answers.items():
        questionnaire_warning_thresholds[questionnaire] = max(settings.RESULTS_WARNING_PERCENTAGE * median(max_answers_list), settings.RESULTS_WARNING_COUNT)

    for questionnaire_result in evaluation_result.questionnaire_results:
        rating_results = [question_result for question_result in questionnaire_result.question_results if question_result.question.is_rating_question]
        max_answers = max((rating_result.count_sum for rating_result in rating_results), default=0)
        questionnaire_result.warning = 0 < max_answers < questionnaire_warning_thresholds[questionnaire_result.questionnaire]

        for rating_result in rating_results:
            rating_result.warning = questionnaire_result.warning or rating_result.has_answers and rating_result.count_sum < questionnaire_warning_thresholds[questionnaire_result.questionnaire]
