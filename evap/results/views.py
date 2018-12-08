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

from evap.evaluation.models import Semester, Degree, Contribution, Evaluation, CourseType, UserProfile
from evap.evaluation.auth import internal_required
from evap.results.tools import collect_results, calculate_average_distribution, distribution_to_grade, \
    TextAnswer, TextResult, HeadingResult, get_single_result_rating_result


def get_evaluation_result_template_fragment_cache_key(evaluation_id, language, can_user_see_results_page):
    return make_template_fragment_key('evaluation_result_template_fragment', [evaluation_id, language, can_user_see_results_page])


def delete_template_cache(evaluation):
    assert evaluation.state != 'published'
    _delete_template_cache_impl(evaluation)


def _delete_template_cache_impl(evaluation):
    caches['results'].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, 'en', True))
    caches['results'].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, 'en', False))
    caches['results'].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, 'de', True))
    caches['results'].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, 'de', False))


def warm_up_template_cache(evaluations):
    evaluations = get_evaluations_with_prefetched_data(evaluations)
    current_language = translation.get_language()
    try:
        for evaluation in evaluations:
            assert evaluation.state == 'published'
            translation.activate('en')
            get_template('results_index_evaluation.html').render(dict(evaluation=evaluation, can_user_see_results_page=True))
            get_template('results_index_evaluation.html').render(dict(evaluation=evaluation, can_user_see_results_page=False))
            translation.activate('de')
            get_template('results_index_evaluation.html').render(dict(evaluation=evaluation, can_user_see_results_page=True))
            get_template('results_index_evaluation.html').render(dict(evaluation=evaluation, can_user_see_results_page=False))
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


def get_evaluations_with_prefetched_data(evaluations):
    if isinstance(evaluations, QuerySet):
        participant_counts = evaluations.annotate(num_participants=Count("participants")).values_list("num_participants", flat=True)
        voter_counts = evaluations.annotate(num_voters=Count("voters")).values_list("num_voters", flat=True)
        evaluations = (evaluations
            .select_related("type")
            .prefetch_related(
                "degrees",
                "semester",
                Prefetch("contributions", queryset=Contribution.objects.filter(responsible=True).select_related("contributor"), to_attr="responsible_contributions")
            )
        )
        for evaluation, participant_count, voter_count in zip(evaluations, participant_counts, voter_counts):
            if evaluation._participant_count is None:
                evaluation.num_participants = participant_count
                evaluation.num_voters = voter_count
            evaluation.responsible_contributors = [contribution.contributor for contribution in evaluation.responsible_contributions]
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
    evaluations = Evaluation.objects.filter(semester__in=semesters, state='published')
    evaluations = [evaluation for evaluation in evaluations if evaluation.can_user_see_evaluation(request.user)]

    if request.user.is_reviewer:
        additional_evaluations = Evaluation.objects.filter(semester__in=semesters, state__in=['in_evaluation', 'evaluated', 'reviewed'])
        evaluations += get_evaluations_with_prefetched_data(additional_evaluations)

    evaluation_pks = [evaluation.pk for evaluation in evaluations]
    degrees = Degree.objects.filter(evaluations__pk__in=evaluation_pks).distinct()
    course_types = CourseType.objects.filter(evaluations__pk__in=evaluation_pks).distinct()
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
    evaluation = get_object_or_404(semester.evaluations, id=evaluation_id, semester=semester)

    if not evaluation.can_user_see_results_page(request.user):
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
                question_result.answers = [answer for answer in question_result.answers if user_can_see_textanswer(view_as_user, represented_users, answer, view)]
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

    evaluation.distribution = calculate_average_distribution(evaluation)
    evaluation.avg_grade = distribution_to_grade(evaluation.distribution)

    other_contributors = []
    if view == 'export':
        other_contributors = [contribution_result.contributor for contribution_result in evaluation_result.contribution_results if contribution_result.contributor not in [None, view_as_user]]

    template_data = dict(
        evaluation=evaluation,
        general_questionnaire_results_top=general_questionnaire_results_top,
        general_questionnaire_results_bottom=general_questionnaire_results_bottom,
        contributor_contribution_results=contributor_contribution_results,
        is_reviewer=view_as_user.is_reviewer,
        is_contributor=evaluation.is_user_contributor(view_as_user),
        is_contributor_or_delegate=evaluation.is_user_contributor_or_delegate(view_as_user),
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


def user_can_see_textanswer(user, represented_users, textanswer, view):
    assert textanswer.state in [TextAnswer.PRIVATE, TextAnswer.PUBLISHED]
    contributor = textanswer.contribution.contributor

    if view == 'public':
        return False
    elif view == 'export':
        if textanswer.is_private:
            return False
        if not textanswer.contribution.is_general and contributor != user:
            return False
    elif user.is_reviewer:
        return True

    if textanswer.is_private:
        return contributor == user

    # NOTE: when changing this behavior, make sure all changes are also reflected in results.tools.textanswers_visible_to
    # and in results.tests.test_tools.TestTextAnswerVisibilityInfo
    if textanswer.is_published:
        # text answers about responsible contributors can only be seen by the users themselves and by their delegates
        # they can not be seen by other responsible contributors
        if textanswer.contribution.responsible:
            return contributor in represented_users

        # users can see textanswers if the contributor is one of their represented users (which includes the user itself)
        if contributor in represented_users:
            return True
        # users can see text answers from general contributions if one of their represented users has text answer
        # visibility GENERAL_TEXTANSWERS for the evaluation
        if textanswer.contribution.is_general and textanswer.contribution.evaluation.contributions.filter(
                contributor__in=represented_users, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS).exists():
            return True

    return False
