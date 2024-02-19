from collections import defaultdict
from statistics import median

from django.conf import settings
from django.core.cache import caches
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import BadRequest, PermissionDenied
from django.db.models import Count, QuerySet
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template
from django.utils import translation

from evap.evaluation.auth import internal_required
from evap.evaluation.models import Course, CourseType, Degree, Evaluation, Semester, UserProfile
from evap.evaluation.tools import AttachmentResponse, unordered_groupby
from evap.results.exporters import TextAnswerExporter
from evap.results.tools import (
    STATES_WITH_RESULT_TEMPLATE_CACHING,
    HeadingResult,
    RatingResult,
    TextResult,
    annotate_distributions_and_grades,
    can_textanswer_be_seen_by,
    get_evaluations_with_course_result_attributes,
    get_results,
)


def get_course_result_template_fragment_cache_key(course_id, language):
    return make_template_fragment_key("course_result_template_fragment", [course_id, language])


def get_evaluation_result_template_fragment_cache_key(evaluation_id, language, links_to_results_page):
    return make_template_fragment_key(
        "evaluation_result_template_fragment", [evaluation_id, language, links_to_results_page]
    )


def delete_template_cache(evaluation):
    assert evaluation.state not in STATES_WITH_RESULT_TEMPLATE_CACHING
    _delete_template_cache_impl(evaluation)


def _delete_template_cache_impl(evaluation):
    _delete_evaluation_template_cache_impl(evaluation)
    _delete_course_template_cache_impl(evaluation.course)


def _delete_evaluation_template_cache_impl(evaluation):
    caches["results"].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", True))
    caches["results"].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", False))
    caches["results"].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", True))
    caches["results"].delete(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", False))


def _delete_course_template_cache_impl(course):
    caches["results"].delete(get_course_result_template_fragment_cache_key(course.id, "en"))
    caches["results"].delete(get_course_result_template_fragment_cache_key(course.id, "de"))


def update_template_cache(evaluations):
    assert all(evaluation.state in STATES_WITH_RESULT_TEMPLATE_CACHING for evaluation in evaluations)
    evaluations = get_evaluations_with_course_result_attributes(get_evaluations_with_prefetched_data(evaluations))

    courses_and_evaluations = unordered_groupby((evaluation.course, evaluation) for evaluation in evaluations)

    current_language = translation.get_language()

    results_index_course_template = get_template("results_index_course_impl.html", using="CachedEngine")
    results_index_evaluation_template = get_template("results_index_evaluation_impl.html", using="CachedEngine")

    try:
        for lang in ["en", "de"]:
            translation.activate(lang)

            for course, course_evaluations in courses_and_evaluations.items():
                if len(course_evaluations) > 1:
                    caches["results"].set(
                        get_course_result_template_fragment_cache_key(course.id, lang),
                        results_index_course_template.render({"course": course, "evaluations": course_evaluations}),
                    )

                for evaluation in course_evaluations:
                    assert evaluation.state in STATES_WITH_RESULT_TEMPLATE_CACHING
                    base_args = {"evaluation": evaluation, "is_subentry": len(course_evaluations) > 1}

                    caches["results"].set(
                        get_evaluation_result_template_fragment_cache_key(evaluation.id, lang, True),
                        results_index_evaluation_template.render({**base_args, "links_to_results_page": True}),
                    )
                    caches["results"].set(
                        get_evaluation_result_template_fragment_cache_key(evaluation.id, lang, False),
                        results_index_evaluation_template.render({**base_args, "links_to_results_page": False}),
                    )

    finally:
        translation.activate(current_language)  # reset to previously set language to prevent unwanted side effects


def update_template_cache_of_published_evaluations_in_course(course):
    # Delete template caches for evaluations that no longer need to be cached (e.g. after unpublishing)
    _delete_course_template_cache_impl(course)

    course_evaluations = course.evaluations.filter(state__in=STATES_WITH_RESULT_TEMPLATE_CACHING)
    update_template_cache(course_evaluations)


def get_evaluations_with_prefetched_data(evaluations):
    if isinstance(evaluations, QuerySet):  # type: ignore
        evaluations = evaluations.select_related("course__type").prefetch_related(
            "course__degrees",
            "course__semester",
            "course__responsibles",
        )
        evaluations = Evaluation.annotate_with_participant_and_voter_counts(evaluations)

    annotate_distributions_and_grades(evaluations)

    return evaluations


@internal_required
def index(request):
    semesters = Semester.get_all_with_published_unarchived_results()
    evaluations = Evaluation.objects.filter(course__semester__in=semesters, state=Evaluation.State.PUBLISHED)
    evaluations = evaluations.select_related("course", "course__semester")
    evaluations = [evaluation for evaluation in evaluations if evaluation.can_be_seen_by(request.user)]

    if request.user.is_reviewer:
        additional_evaluations = get_evaluations_with_prefetched_data(
            Evaluation.objects.filter(
                course__semester__in=semesters,
                state__in=[Evaluation.State.IN_EVALUATION, Evaluation.State.EVALUATED, Evaluation.State.REVIEWED],
            )
        )
        additional_evaluations = get_evaluations_with_course_result_attributes(additional_evaluations)
        evaluations += additional_evaluations

    # put evaluations into a dict that maps from course to a list of evaluations.
    # this dict is sorted by course.pk (important for the zip below)
    # (this relies on python 3.7's guarantee that the insertion order of the dict is preserved)
    evaluations.sort(key=lambda evaluation: evaluation.course.pk)
    courses_and_evaluations = unordered_groupby((evaluation.course, evaluation) for evaluation in evaluations)

    course_pks = [course.pk for course in courses_and_evaluations.keys()]

    # annotate each course in courses with num_evaluations
    annotated_courses = (
        Course.objects.filter(pk__in=course_pks).annotate(num_evaluations=Count("evaluations")).order_by("pk").defer()
    )
    for course, annotated_course in zip(courses_and_evaluations.keys(), annotated_courses):
        course.num_evaluations = annotated_course.num_evaluations

    degrees = Degree.objects.filter(courses__pk__in=course_pks).distinct()
    course_types = CourseType.objects.filter(courses__pk__in=course_pks).distinct()
    template_data = {
        "courses_and_evaluations": courses_and_evaluations.items(),
        "degrees": degrees,
        "course_types": course_types,
        "semesters": semesters,
    }
    return render(request, "results_index.html", template_data)


def evaluation_detail(request, semester_id, evaluation_id):
    # pylint: disable=too-many-locals
    semester = get_object_or_404(Semester, id=semester_id)
    evaluation = get_object_or_404(semester.evaluations, id=evaluation_id, course__semester=semester)

    view, view_as_user, represented_users, contributor_id = evaluation_detail_parse_get_parameters(request, evaluation)

    evaluation_result = get_results(evaluation)
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
    if view == "export":
        contributors_with_omitted_results = [
            contribution_result.contributor
            for contribution_result in evaluation_result.contribution_results
            if contribution_result.contributor not in [None, view_as_user]
        ]

    # if the results are not cached, we need to attach distribution
    # information for rendering the distribution bar
    if evaluation.state not in STATES_WITH_RESULT_TEMPLATE_CACHING:
        prefetched = get_evaluations_with_prefetched_data([evaluation])
        evaluation = get_evaluations_with_course_result_attributes(prefetched)[0]

    is_responsible_or_contributor_or_delegate = evaluation.is_user_responsible_or_contributor_or_delegate(view_as_user)

    template_data = {
        "evaluation": evaluation,
        "course": evaluation.course,
        "course_evaluations": course_evaluations,
        "general_questionnaire_results_top": top_results,
        "general_questionnaire_results_bottom": bottom_results,
        "contributor_contribution_results": contributor_results,
        "is_reviewer": view_as_user.is_reviewer,
        "is_contributor": evaluation.is_user_contributor(view_as_user),
        "is_responsible_or_contributor_or_delegate": is_responsible_or_contributor_or_delegate,
        "can_download_grades": view_as_user.can_download_grades,
        "can_export_text_answers": (
            view in ("export", "full") and (view_as_user.is_reviewer or is_responsible_or_contributor_or_delegate)
        ),
        "view": view,
        "view_as_user": view_as_user,
        "contributors_with_omitted_results": contributors_with_omitted_results,
        "contributor_id": contributor_id,
    }
    return render(request, "results_evaluation_detail.html", template_data)


def remove_textanswers_that_the_user_must_not_see(evaluation_result, user, represented_users, view):
    for questionnaire_result in evaluation_result.questionnaire_results:
        for question_result in questionnaire_result.question_results:
            if isinstance(question_result, TextResult):
                question_result.answers = [
                    answer
                    for answer in question_result.answers
                    if can_textanswer_be_seen_by(user, represented_users, answer, view)
                ]
            if isinstance(question_result, RatingResult) and question_result.additional_text_result:
                question_result.additional_text_result.answers = [
                    answer
                    for answer in question_result.additional_text_result.answers
                    if can_textanswer_be_seen_by(user, represented_users, answer, view)
                ]
        # remove empty TextResults
        cleaned_results = []
        for result in questionnaire_result.question_results:
            if isinstance(result, TextResult):
                if result.answers:
                    cleaned_results.append(result)
            elif isinstance(result, HeadingResult):
                cleaned_results.append(result)
            else:
                if result.additional_text_result and not result.additional_text_result.answers:
                    result.additional_text_result = None
                cleaned_results.append(result)
        questionnaire_result.question_results = cleaned_results


def filter_text_answers(evaluation_result):
    for questionnaire_result in evaluation_result.questionnaire_results:
        question_results = []
        for result in questionnaire_result.question_results:
            if isinstance(result, TextResult):
                question_results.append(result)
            elif isinstance(result, RatingResult) and result.additional_text_result:
                question_results.append(result.additional_text_result)
        questionnaire_result.question_results = question_results


def exclude_empty_headings(evaluation_result):
    for questionnaire_result in evaluation_result.questionnaire_results:
        filtered_question_results = []
        for i, question_result in enumerate(questionnaire_result.question_results):
            # filter out if there are no more questions or the next question is also a heading question
            if isinstance(question_result, HeadingResult):
                if i == len(questionnaire_result.question_results) - 1 or isinstance(
                    questionnaire_result.question_results[i + 1], HeadingResult
                ):
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
        elif view != "export" or view_as_user.id == contribution_result.contributor.id:
            contributor_results.append(contribution_result)

    if not contributor_results:
        top_results += bottom_results
        bottom_results = []

    return top_results, bottom_results, contributor_results


def get_evaluations_of_course(course, request):
    course_evaluations = []

    if course.evaluations.count() > 1:
        course_evaluations = [
            evaluation
            for evaluation in course.evaluations.filter(state=Evaluation.State.PUBLISHED)
            if evaluation.can_be_seen_by(request.user)
        ]
        if request.user.is_reviewer:
            course_evaluations += course.evaluations.filter(
                state__in=[Evaluation.State.IN_EVALUATION, Evaluation.State.EVALUATED, Evaluation.State.REVIEWED]
            )
        annotate_distributions_and_grades(course_evaluations)
        course_evaluations = get_evaluations_with_course_result_attributes(course_evaluations)

    return course_evaluations


def add_warnings(evaluation, evaluation_result):
    if not evaluation.can_publish_rating_results:
        return

    # calculate the median values of how many people answered a questionnaire across all contributions
    questionnaire_max_answers = defaultdict(list)
    for questionnaire_result in evaluation_result.questionnaire_results:
        max_answers = max(
            (
                question_result.count_sum
                for question_result in questionnaire_result.question_results
                if question_result.question.is_rating_question
            ),
            default=0,
        )
        questionnaire_max_answers[questionnaire_result.questionnaire].append(max_answers)

    questionnaire_warning_thresholds = {}
    for questionnaire, max_answers_list in questionnaire_max_answers.items():
        questionnaire_warning_thresholds[questionnaire] = max(
            settings.RESULTS_WARNING_PERCENTAGE * median(max_answers_list), settings.RESULTS_WARNING_COUNT
        )

    for questionnaire_result in evaluation_result.questionnaire_results:
        rating_results = [
            question_result
            for question_result in questionnaire_result.question_results
            if question_result.question.is_rating_question
        ]
        max_answers = max((rating_result.count_sum for rating_result in rating_results), default=0)
        questionnaire_result.warning = (
            0 < max_answers < questionnaire_warning_thresholds[questionnaire_result.questionnaire]
        )

        for rating_result in rating_results:
            rating_result.warning = (
                questionnaire_result.warning
                or RatingResult.has_answers(rating_result)
                and rating_result.count_sum < questionnaire_warning_thresholds[questionnaire_result.questionnaire]
            )


def evaluation_detail_parse_get_parameters(request, evaluation):
    if not evaluation.can_results_page_be_seen_by(request.user):
        raise PermissionDenied

    view = request.GET.get("view", "public" if request.user.is_reviewer else "full")
    if view not in ["public", "full", "export"]:
        view = "public"

    view_as_user = request.user
    try:
        contributor = get_object_or_404(UserProfile, pk=request.GET.get("contributor_id", request.user.id))
    except ValueError as e:
        raise BadRequest from e

    if view == "export" and request.user.is_staff:
        view_as_user = contributor
    contributor_id = contributor.pk if contributor != request.user else None

    represented_users = [view_as_user]
    if view != "export":
        represented_users += list(view_as_user.represented_users.all())
    # redirect to non-public view if there is none because the results have not been published
    if not evaluation.can_publish_rating_results and view == "public":
        view = "full"

    return view, view_as_user, represented_users, contributor_id


def extract_evaluation_answer_data(request, evaluation):
    # TextAnswerExporter wants a dict from Question to tuple of contributor_name and string list (of the answers)

    view, view_as_user, represented_users, contributor_id = evaluation_detail_parse_get_parameters(request, evaluation)

    evaluation_result = get_results(evaluation)
    filter_text_answers(evaluation_result)
    remove_textanswers_that_the_user_must_not_see(evaluation_result, view_as_user, represented_users, view)

    results = TextAnswerExporter.InputData(evaluation_result.contribution_results)

    return results, contributor_id


def evaluation_text_answers_export(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    results, contributor_id = extract_evaluation_answer_data(request, evaluation)
    contributor_name = UserProfile.objects.get(id=contributor_id).full_name if contributor_id is not None else None

    filename = f"Evaluation-Text-Answers-{evaluation.course.semester.short_name}-{evaluation.full_name}-{translation.get_language()}.xls"

    response = AttachmentResponse(filename, content_type="application/vnd.ms-excel")

    TextAnswerExporter(
        evaluation.full_name,
        evaluation.course.semester.name,
        evaluation.course.responsibles_names,
        results,
        contributor_name,
    ).export(response)

    return response
