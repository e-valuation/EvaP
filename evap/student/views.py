import datetime
import math
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, F, Max, OuterRef, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from evap.evaluation.auth import participant_required
from evap.evaluation.models import NO_ANSWER, Evaluation, RatingAnswerCounter, Semester, TextAnswer, VoteTimestamp
from evap.results.tools import (
    annotate_distributions_and_grades,
    get_evaluations_with_course_result_attributes,
    textanswers_visible_to,
)
from evap.student.forms import QuestionnaireVotingForm
from evap.student.models import TextAnswerWarning
from evap.student.tools import answer_field_id

SUCCESS_MAGIC_STRING = "vote submitted successfully"


@dataclass
class GlobalRewards:
    @dataclass
    class RewardProgress:
        progress: Fraction  # progress towards this reward, relative to max reward, between 0 and 1
        vote_ratio: Fraction
        text: str

    vote_count: int
    participation_count: int
    max_reward_votes: int
    bar_width_votes: int
    last_vote_datetime: datetime.datetime
    rewards_with_progress: list[RewardProgress]
    info_text: str

    @staticmethod
    def from_settings() -> "GlobalRewards | None":
        if not settings.GLOBAL_EVALUATION_PROGRESS_REWARDS:
            return None

        if not Semester.active_semester():
            return None

        evaluations = (
            Semester.active_semester()
            .evaluations.filter(is_single_result=False)
            .exclude(state__lt=Evaluation.State.APPROVED)
            .exclude(is_rewarded=False)
            .exclude(id__in=settings.GLOBAL_EVALUATION_PROGRESS_EXCLUDED_EVALUATION_IDS)
            .exclude(course__type__id__in=settings.GLOBAL_EVALUATION_PROGRESS_EXCLUDED_COURSE_TYPE_IDS)
            .exclude(course__is_private=True)
        )

        vote_count, participation_count = (
            Evaluation.annotate_with_participant_and_voter_counts(evaluations)
            .aggregate(Sum("num_voters", default=0), Sum("num_participants", default=0))
            .values()
        )

        max_reward_vote_ratio, __ = max(settings.GLOBAL_EVALUATION_PROGRESS_REWARDS)
        max_reward_votes = math.ceil(max_reward_vote_ratio * participation_count)

        rewards_with_progress = [
            GlobalRewards.RewardProgress(progress=vote_ratio / max_reward_vote_ratio, vote_ratio=vote_ratio, text=text)
            for vote_ratio, text in settings.GLOBAL_EVALUATION_PROGRESS_REWARDS
        ]

        last_vote_datetime = VoteTimestamp.objects.filter(evaluation__in=evaluations).aggregate(Max("timestamp"))[
            "timestamp__max"
        ]

        return GlobalRewards(
            vote_count=vote_count,
            participation_count=participation_count,
            max_reward_votes=max_reward_votes,
            bar_width_votes=min(vote_count, max_reward_votes),
            last_vote_datetime=last_vote_datetime,
            rewards_with_progress=rewards_with_progress,
            info_text=settings.GLOBAL_EVALUATION_PROGRESS_INFO_TEXT[get_language()],
        )


@participant_required
def index(request):
    query = (
        Evaluation.objects.annotate(
            participates_in=Exists(Evaluation.objects.filter(id=OuterRef("id"), participants=request.user))
        )
        .annotate(voted_for=Exists(Evaluation.objects.filter(id=OuterRef("id"), voters=request.user)))
        .filter(~Q(state=Evaluation.State.NEW), course__evaluations__participants=request.user)
        .exclude(state=Evaluation.State.NEW)
        .prefetch_related(
            "course",
            "course__semester",
            "course__grade_documents",
            "course__type",
            "course__evaluations",
            "course__responsibles",
            "course__programs",
        )
        .distinct()
    )
    query = Evaluation.annotate_with_participant_and_voter_counts(query)
    evaluations = [evaluation for evaluation in query if evaluation.can_be_seen_by(request.user)]

    inner_evaluation_ids = [
        inner_evaluation.id for evaluation in evaluations for inner_evaluation in evaluation.course.evaluations.all()
    ]
    inner_evaluation_query = Evaluation.objects.filter(pk__in=inner_evaluation_ids)
    inner_evaluation_query = Evaluation.annotate_with_participant_and_voter_counts(inner_evaluation_query)

    evaluations_by_id = {evaluation["id"]: evaluation for evaluation in inner_evaluation_query.values()}

    for evaluation in evaluations:
        for inner_evaluation in evaluation.course.evaluations.all():
            inner_evaluation.num_voters = evaluations_by_id[inner_evaluation.id]["num_voters"]
            inner_evaluation.num_participants = evaluations_by_id[inner_evaluation.id]["num_participants"]

    annotate_distributions_and_grades(e for e in evaluations if e.state == Evaluation.State.PUBLISHED)
    evaluations = get_evaluations_with_course_result_attributes(evaluations)

    # evaluations must be sorted for regrouping them in the template
    evaluations.sort(key=lambda evaluation: (evaluation.course.name, evaluation.name))

    semesters = Semester.objects.all()
    semester_list = [
        {
            "semester_name": semester.name,
            "id": semester.id,
            "results_are_archived": semester.results_are_archived,
            "grade_documents_are_deleted": semester.grade_documents_are_deleted,
            "evaluations": [evaluation for evaluation in evaluations if evaluation.course.semester_id == semester.id],
        }
        for semester in semesters
    ]

    unfinished_evaluations_query = (
        Evaluation.objects.filter(
            participants=request.user,
            state__in=[
                Evaluation.State.PREPARED,
                Evaluation.State.EDITOR_APPROVED,
                Evaluation.State.APPROVED,
                Evaluation.State.IN_EVALUATION,
            ],
        )
        .exclude(voters=request.user)
        .prefetch_related("course__responsibles", "course__type", "course__semester")
    )

    unfinished_evaluations_query = Evaluation.annotate_with_participant_and_voter_counts(unfinished_evaluations_query)
    unfinished_evaluations = list(unfinished_evaluations_query)

    # available evaluations come first, ordered by time left for evaluation and the name
    # evaluations in other (visible) states follow by name
    def sorter(evaluation):
        return (
            evaluation.state != Evaluation.State.IN_EVALUATION,
            evaluation.vote_end_date if evaluation.state == Evaluation.State.IN_EVALUATION else None,
            evaluation.full_name,
        )

    unfinished_evaluations.sort(key=sorter)

    template_data = {
        "semester_list": semester_list,
        "can_download_grades": request.user.can_download_grades,
        "unfinished_evaluations": unfinished_evaluations,
        "evaluation_end_warning_period": settings.EVALUATION_END_WARNING_PERIOD,
        "global_rewards": GlobalRewards.from_settings(),
    }

    return render(request, "student_index.html", template_data)


def get_vote_page_form_groups(request, evaluation, preview):
    contributions_to_vote_on = evaluation.contributions.all()
    # prevent a user from voting on themselves
    if not preview:
        contributions_to_vote_on = contributions_to_vote_on.exclude(contributor=request.user)

    form_groups = OrderedDict()
    for contribution in contributions_to_vote_on:
        questionnaires = contribution.questionnaires.all()
        if not questionnaires.exists():
            continue
        form_groups[contribution] = [
            QuestionnaireVotingForm(request.POST or None, contribution=contribution, questionnaire=questionnaire)
            for questionnaire in questionnaires
        ]
    return form_groups


def render_vote_page(request, evaluation, preview, for_rendering_in_modal=False):
    form_groups = get_vote_page_form_groups(request, evaluation, preview)

    assert preview or not all(form.is_valid() for form_group in form_groups.values() for form in form_group)

    evaluation_form_group = form_groups.pop(evaluation.general_contribution, default=[])

    contributor_form_groups = [
        (
            contribution.contributor,
            contribution.label,
            form_group,
            any(form.errors for form in form_group),
            textanswers_visible_to(contribution),
        )
        for contribution, form_group in form_groups.items()
    ]
    evaluation_form_group_top = [
        questions_form for questions_form in evaluation_form_group if questions_form.questionnaire.is_above_contributors
    ]
    evaluation_form_group_bottom = [
        questions_form for questions_form in evaluation_form_group if questions_form.questionnaire.is_below_contributors
    ]
    if not contributor_form_groups:
        evaluation_form_group_top += evaluation_form_group_bottom
        evaluation_form_group_bottom = []

    contributor_errors_exist = any(form.errors for form_group in form_groups.values() for form in form_group)
    errors_exist = contributor_errors_exist or any(
        any(form.errors for form in form_group)
        for form_group in [evaluation_form_group_top, evaluation_form_group_bottom]
    )

    template_data = {
        "contributor_errors_exist": contributor_errors_exist,
        "errors_exist": errors_exist,
        "evaluation_form_group_top": evaluation_form_group_top,
        "evaluation_form_group_bottom": evaluation_form_group_bottom,
        "contributor_form_groups": contributor_form_groups,
        "evaluation": evaluation,
        "small_evaluation_size_warning": evaluation.num_participants <= settings.SMALL_COURSE_SIZE,
        "preview": preview,
        "success_magic_string": SUCCESS_MAGIC_STRING,
        "success_redirect_url": reverse("student:index"),
        "for_rendering_in_modal": for_rendering_in_modal,
        "general_contribution_textanswers_visible_to": textanswers_visible_to(evaluation.general_contribution),
        "text_answer_warnings": TextAnswerWarning.objects.all(),
    }
    return render(request, "student_vote.html", template_data)


@participant_required
def vote(request, evaluation_id):  # noqa: PLR0912
    # pylint: disable=too-many-nested-blocks
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    if not evaluation.can_be_voted_for_by(request.user):
        raise PermissionDenied

    form_groups = get_vote_page_form_groups(request, evaluation, preview=False)
    if not all(form.is_valid() for form_group in form_groups.values() for form in form_group):
        return render_vote_page(request, evaluation, preview=False)

    # all forms are valid, begin vote operation
    with transaction.atomic():
        # add user to evaluation.voters
        # not using evaluation.voters.add(request.user) since that fails silently when done twice.
        evaluation.voters.through.objects.create(userprofile_id=request.user.pk, evaluation_id=evaluation.pk)

        for contribution, form_group in form_groups.items():
            for questionnaire_form in form_group:
                questionnaire = questionnaire_form.questionnaire
                for question in questionnaire.questions.all():
                    if question.is_heading_question:
                        continue

                    identifier = answer_field_id(contribution, questionnaire, question)
                    value = questionnaire_form.cleaned_data.get(identifier)

                    if question.is_text_question:
                        if value:
                            question.answer_class.objects.create(
                                contribution=contribution, question=question, answer=value
                            )
                    else:
                        if value != NO_ANSWER:
                            answer_counter, __ = question.answer_class.objects.get_or_create(
                                contribution=contribution, question=question, answer=value
                            )
                            answer_counter.count += 1
                            answer_counter.save()
                        if question.allows_additional_textanswers:
                            textanswer_identifier = answer_field_id(
                                contribution, questionnaire, question, additional_textanswer=True
                            )
                            textanswer_value = questionnaire_form.cleaned_data.get(textanswer_identifier)
                            if textanswer_value:
                                TextAnswer.objects.create(
                                    contribution=contribution, question=question, answer=textanswer_value
                                )

        VoteTimestamp.objects.create(evaluation=evaluation)

        # Update all answer rows to make sure no system columns give away which one was last modified
        # see https://github.com/e-valuation/EvaP/issues/1384
        RatingAnswerCounter.objects.filter(contribution__evaluation=evaluation).update(id=F("id"))
        TextAnswer.objects.filter(contribution__evaluation=evaluation).update(id=F("id"))

        if not evaluation.can_publish_text_results:
            # enable text result publishing if first user confirmed that publishing is okay or second user voted
            if (
                request.POST.get("text_results_publish_confirmation_top") == "on"
                or request.POST.get("text_results_publish_confirmation_bottom") == "on"
                or evaluation.voters.count() >= 2
            ):
                evaluation.can_publish_text_results = True
                evaluation.save()

        evaluation.evaluation_evaluated.send(sender=Evaluation, request=request, semester=evaluation.course.semester)

    messages.success(request, _("Your vote was recorded."))
    return HttpResponse(SUCCESS_MAGIC_STRING)
