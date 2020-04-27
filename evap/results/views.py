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

from evap.evaluation.models import Semester, Degree, Evaluation, CourseType, UserProfile, Course
from evap.evaluation.auth import internal_required
from evap.evaluation.tools import FileResponse
from evap.results.exporters import TextAnswerExcelExporter
from evap.results.tools import (collect_results, calculate_average_distribution, distribution_to_grade,
                                get_evaluations_with_course_result_attributes, get_single_result_rating_result,
                                HeadingResult, TextResult, can_textanswer_be_seen_by, normalized_distribution)


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
    courses_to_render = {evaluation.course for evaluation in evaluations if evaluation.course.evaluation_count > 1}
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
        # these annotates and the zip below could be replaced by something like this, but it was 2x slower:
        # annotate(num_participants=Coalesce('_participant_count', Count("participants", distinct=True)))
        participant_counts = evaluations.annotate(num_participants=Count("participants")).order_by('pk').values_list("num_participants", flat=True)
        voter_counts = evaluations.annotate(num_voters=Count("voters")).order_by('pk').values_list("num_voters", flat=True)
        course_evaluations_counts = evaluations.annotate(num_course_evaluations=Count("course__evaluations")).order_by('pk').values_list("num_course_evaluations", flat=True)
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
        else:
            evaluation.single_result_rating_result = get_single_result_rating_result(evaluation)
            evaluation.distribution = normalized_distribution(evaluation.single_result_rating_result.counts)
        evaluation.avg_grade = distribution_to_grade(evaluation.distribution)
    return evaluations


@internal_required
def index(request):
    semesters = Semester.get_all_with_published_unarchived_results()
    evaluations = Evaluation.objects.filter(course__semester__in=semesters, state='published')
    evaluations = evaluations.select_related('course', 'course__semester')
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

    # put evaluations into a dict that maps from course to a list of evaluations.
    # this dict is sorted by course.pk (important for the zip below)
    # (this relies on python 3.7's guarantee that the insertion order of the dict is preserved)
    evaluations.sort(key=lambda evaluation: evaluation.course.pk)

    courses_and_evaluations = defaultdict(list)
    for evaluation in evaluations:
        courses_and_evaluations[evaluation.course].append(evaluation)

    course_pks = list([course.pk for course in courses_and_evaluations.keys()])

    # annotate each course in courses with num_evaluations
    annotated_courses = Course.objects.filter(pk__in=course_pks).annotate(num_evaluations=Count('evaluations')).order_by('pk').defer()
    for course, annotated_course in zip(courses_and_evaluations.keys(), annotated_courses):
        course.num_evaluations = annotated_course.num_evaluations

    degrees = Degree.objects.filter(courses__pk__in=course_pks).distinct()
    course_types = CourseType.objects.filter(courses__pk__in=course_pks).distinct()
    template_data = dict(
        courses_and_evaluations=courses_and_evaluations.items(),
        degrees=degrees,
        course_types=course_types,
        semesters=semesters,
    )
    return render(request, "results_index.html", template_data)


@login_required
def evaluation_detail(request, semester_id, evaluation_id):
    # pylint: disable=too-many-locals
    semester = get_object_or_404(Semester, id=semester_id)
    evaluation = get_object_or_404(semester.evaluations, id=evaluation_id, course__semester=semester)

    view, view_as_user, represented_users, contributor_id = evaluation_detail_parse_get_parameters(request, evaluation)

    evaluation_result = collect_results(evaluation)
    remove_textanswers_that_the_user_must_not_see(evaluation_result, view_as_user, represented_users, view)
    exclude_empty_headings(evaluation_result)
    remove_empty_questionnaire_and_contribution_results(evaluation_result)
    add_warnings(evaluation, evaluation_result)

    top_results, bottom_results, contributor_results = split_evaluation_result_into_top_bottom_and_contributor(
        evaluation_result, view_as_user, view
    )

    course_evaluations = get_evaluations_of_course(evaluation.course, request)
    course_evaluations.sort(key=lambda evaluation: evaluation.name)

    contributors_with_omitted_results = []
    if view == 'export':
        contributors_with_omitted_results = [
            contribution_result.contributor
            for contribution_result in evaluation_result.contribution_results
            if contribution_result.contributor not in [None, view_as_user]
        ]

    # if the evaluation is not published, the rendered results are not cached, so we need to attach distribution
    # information for rendering the distribution bar
    if evaluation.state != 'published':
        evaluation = get_evaluations_with_course_result_attributes(get_evaluations_with_prefetched_data([evaluation]))[0]

    is_responsible_or_contributor_or_delegate = evaluation.is_user_responsible_or_contributor_or_delegate(view_as_user)

    template_data = dict(
        evaluation=evaluation,
        course=evaluation.course,
        course_evaluations=course_evaluations,
        general_questionnaire_results_top=top_results,
        general_questionnaire_results_bottom=bottom_results,
        contributor_contribution_results=contributor_results,
        is_reviewer=view_as_user.is_reviewer,
        is_contributor=evaluation.is_user_contributor(view_as_user),
        is_responsible_or_contributor_or_delegate=is_responsible_or_contributor_or_delegate,
        can_download_grades=view_as_user.can_download_grades,
        can_export_text_answers=(view in ("export", "full") and (view_as_user.is_reviewer or is_responsible_or_contributor_or_delegate)),
        view=view,
        view_as_user=view_as_user,
        contributors_with_omitted_results=contributors_with_omitted_results,
        contributor_id=contributor_id,
    )
    return render(request, "results_evaluation_detail.html", template_data)


def remove_textanswers_that_the_user_must_not_see(evaluation_result, user, represented_users, view):
    for questionnaire_result in evaluation_result.questionnaire_results:
        for question_result in questionnaire_result.question_results:
            if isinstance(question_result, TextResult):
                question_result.answers = [
                    answer for answer in question_result.answers
                    if can_textanswer_be_seen_by(user, represented_users, answer, view)
                ]
        # remove empty TextResults
        questionnaire_result.question_results = [
            result for result in questionnaire_result.question_results
            if not isinstance(result, TextResult) or len(result.answers) > 0
        ]


def filter_text_answers(evaluation_result):
    for questionnaire_result in evaluation_result.questionnaire_results:
        questionnaire_result.question_results = [result for result in questionnaire_result.question_results if isinstance(result, TextResult)]


def exclude_empty_headings(evaluation_result):
    for questionnaire_result in evaluation_result.questionnaire_results:
        filtered_question_results = []
        for i, question_result in enumerate(questionnaire_result.question_results):
            # filter out if there are no more questions or the next question is also a heading question
            if isinstance(question_result, HeadingResult):
                if i == len(questionnaire_result.question_results) - 1 or isinstance(questionnaire_result.question_results[i + 1], HeadingResult):
                    continue
            filtered_question_results.append(question_result)
        questionnaire_result.question_results = filtered_question_results


def remove_empty_questionnaire_and_contribution_results(evaluation_result):
    for contribution_result in evaluation_result.contribution_results:
        contribution_result.questionnaire_results = [
            questionnaire_result
            for questionnaire_result in contribution_result.questionnaire_results
            if questionnaire_result.question_results
        ]
    evaluation_result.contribution_results = [
        contribution_result
        for contribution_result in evaluation_result.contribution_results
        if contribution_result.questionnaire_results
    ]


def split_evaluation_result_into_top_bottom_and_contributor(evaluation_result, view_as_user, view):
    top_results = []
    bottom_results = []
    contributor_results = []

    for contribution_result in evaluation_result.contribution_results:
        if contribution_result.contributor is None:
            for questionnaire_result in contribution_result.questionnaire_results:
                if questionnaire_result.questionnaire.is_below_contributors:
                    bottom_results.append(questionnaire_result)
                else:
                    top_results.append(questionnaire_result)
        elif view != 'export' or view_as_user.id == contribution_result.contributor.id:
            contributor_results.append(contribution_result)

    if not contributor_results:
        top_results += bottom_results
        bottom_results = []

    return top_results, bottom_results, contributor_results


def get_evaluations_of_course(course, request):
    course_evaluations = []

    if course.evaluations.count() > 1:
        course_evaluations = [evaluation for evaluation in course.evaluations.filter(state="published") if evaluation.can_be_seen_by(request.user)]
        if request.user.is_reviewer:
            course_evaluations += course.evaluations.filter(state__in=['in_evaluation', 'evaluated', 'reviewed'])

        course_evaluations = get_evaluations_with_course_result_attributes(course_evaluations)

        for course_evaluation in course_evaluations:
            if course_evaluation.is_single_result:
                course_evaluation.single_result_rating_result = get_single_result_rating_result(course_evaluation)
            else:
                course_evaluation.distribution = calculate_average_distribution(course_evaluation)
                course_evaluation.avg_grade = distribution_to_grade(course_evaluation.distribution)

    return course_evaluations


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


def evaluation_detail_parse_get_parameters(request, evaluation):
    if not evaluation.can_results_page_be_seen_by(request.user):
        raise PermissionDenied

    if request.user.is_reviewer:
        view = request.GET.get('view', 'public')  # if parameter is not given, show public view.
    else:
        view = request.GET.get('view', 'full')  # if parameter is not given, show own view.
    if view not in ['public', 'full', 'export']:
        view = 'public'

    view_as_user = request.user
    contributor_id = int(request.GET.get('contributor_id', request.user.id))
    if view == 'export' and request.user.is_staff:
        view_as_user = UserProfile.objects.get(id=contributor_id)
    contributor_id = contributor_id if contributor_id != request.user.id else None

    represented_users = [view_as_user]
    if view != 'export':
        represented_users += list(view_as_user.represented_users.all())
    # redirect to non-public view if there is none because the results have not been published
    if not evaluation.can_publish_rating_results and view == 'public':
        view = 'full'

    return view, view_as_user, represented_users, contributor_id


def extract_evaluation_answer_data(request, evaluation):
    # TextAnswerExcelExporter wants a dict from Question to tuple of contributor_name and string list (of the answers)

    view, view_as_user, represented_users, contributor_id = evaluation_detail_parse_get_parameters(request, evaluation)

    evaluation_result = collect_results(evaluation)
    filter_text_answers(evaluation_result)
    remove_textanswers_that_the_user_must_not_see(evaluation_result, view_as_user, represented_users, view)

    results = TextAnswerExcelExporter.InputData(evaluation_result.contribution_results)

    return results, contributor_id


def evaluation_text_answers_export(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    results, contributor_id = extract_evaluation_answer_data(request, evaluation)
    contributor_name = UserProfile.objects.get(id=contributor_id).full_name if contributor_id is not None else None

    filename = "Evaluation-Text-Answers-{}-{}-{}.xls".format(
        evaluation.course.semester.short_name,
        evaluation.full_name,
        translation.get_language()
    )

    response = FileResponse(filename, content_type="application/vnd.ms-excel")

    TextAnswerExcelExporter(evaluation.full_name, evaluation.course.semester.name,
                            evaluation.course.responsibles_names, results, contributor_name).export(response)

    return response
