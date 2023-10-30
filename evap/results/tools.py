from collections import OrderedDict, defaultdict
from collections.abc import Iterable
from copy import copy
from math import ceil, modf
from typing import TypeGuard, cast

from django.conf import settings
from django.core.cache import caches
from django.db.models import Exists, OuterRef, Sum, prefetch_related_objects

from evap.evaluation.models import (
    CHOICES,
    NO_ANSWER,
    Contribution,
    Course,
    Evaluation,
    Question,
    Questionnaire,
    RatingAnswerCounter,
    TextAnswer,
    UserProfile,
)
from evap.evaluation.tools import discard_cached_related_objects, unordered_groupby

STATES_WITH_RESULTS_CACHING = {Evaluation.State.EVALUATED, Evaluation.State.REVIEWED, Evaluation.State.PUBLISHED}
STATES_WITH_RESULT_TEMPLATE_CACHING = {Evaluation.State.PUBLISHED}


GRADE_COLORS = {
    1: (136, 191, 74),
    2: (187, 209, 84),
    3: (239, 226, 88),
    4: (242, 158, 88),
    5: (235, 89, 90),
}


class TextAnswerVisibility:
    def __init__(self, visible_by_contribution: Iterable[UserProfile], visible_by_delegation_count: int):
        self.visible_by_contribution = [discard_cached_related_objects(copy(user)) for user in visible_by_contribution]
        self.visible_by_delegation_count = visible_by_delegation_count


def create_rating_result(question, answer_counters, additional_text_result=None):
    if answer_counters is None:
        return RatingResult(question, additional_text_result)
    if any(counter.count != 0 for counter in answer_counters):
        return AnsweredRatingResult(question, answer_counters, additional_text_result)
    return PublishedRatingResult(question, answer_counters, additional_text_result)


class RatingResult:
    @classmethod
    def is_published(cls, rating_result) -> TypeGuard["PublishedRatingResult"]:
        return isinstance(rating_result, PublishedRatingResult)

    @classmethod
    def has_answers(cls, rating_result) -> TypeGuard["AnsweredRatingResult"]:
        return isinstance(rating_result, AnsweredRatingResult)

    def __init__(self, question, additional_text_result=None) -> None:
        assert question.is_rating_question
        self.question = discard_cached_related_objects(copy(question))
        self.additional_text_result = additional_text_result
        self.colors = tuple(
            color for _, color, value in self.choices.as_name_color_value_tuples() if value != NO_ANSWER
        )

    @property
    def choices(self):
        return CHOICES[self.question.type]


class PublishedRatingResult(RatingResult):
    def __init__(self, question, answer_counters, additional_text_result=None) -> None:
        super().__init__(question, additional_text_result)
        counts = OrderedDict(
            (value, [0, name, color, value]) for (name, color, value) in self.choices.as_name_color_value_tuples()
        )
        counts.pop(NO_ANSWER)
        for answer_counter in answer_counters:
            assert counts[answer_counter.answer][0] == 0
            counts[answer_counter.answer][0] = answer_counter.count
        self.counts = tuple(count for count, _, _, _ in counts.values())
        self.zipped_choices = tuple(counts.values())

    @property
    def count_sum(self) -> int:
        return sum(self.counts)

    @property
    def minus_balance_count(self) -> float:
        assert self.question.is_bipolar_likert_question
        portion_left = sum(self.counts[:3]) + self.counts[3] / 2
        return (self.count_sum - portion_left) / 2

    @property
    def approval_count(self) -> int:
        assert self.question.is_yes_no_question
        return self.counts[0] if self.question.is_positive_yes_no_question else self.counts[1]


class AnsweredRatingResult(PublishedRatingResult):
    @property
    def average(self) -> float:
        return sum(grade * count for count, grade in zip(self.counts, self.choices.grades)) / self.count_sum


class TextResult:
    def __init__(
        self,
        question: Question,
        answers: Iterable[TextAnswer],
        answers_visible_to: TextAnswerVisibility | None = None,
    ):
        assert question.can_have_textanswers
        self.question = discard_cached_related_objects(copy(question))
        self.answers = [discard_cached_related_objects(copy(answer)) for answer in answers]
        self.answers_visible_to = answers_visible_to


class HeadingResult:
    def __init__(self, question: Question):
        self.question = discard_cached_related_objects(copy(question))


QuestionResult = RatingResult | TextResult | HeadingResult


class QuestionnaireResult:
    def __init__(self, questionnaire: Questionnaire, question_results: list[QuestionResult]):
        self.questionnaire = discard_cached_related_objects(copy(questionnaire))
        self.question_results = question_results


class ContributionResult:
    def __init__(
        self, contributor: UserProfile | None, label: str | None, questionnaire_results: list[QuestionnaireResult]
    ):
        self.contributor = discard_cached_related_objects(copy(contributor)) if contributor is not None else None
        self.label = label
        self.questionnaire_results = questionnaire_results

    @property
    def has_answers(self) -> bool:
        for questionnaire_result in self.questionnaire_results:
            for question_result in questionnaire_result.question_results:
                question = question_result.question
                if question.is_text_question:
                    return True
                if question.is_rating_question:
                    assert isinstance(question_result, RatingResult)
                    return RatingResult.has_answers(question_result)
        return False


class EvaluationResult:
    def __init__(self, contribution_results: list[ContributionResult]):
        self.contribution_results = contribution_results

    @property
    def questionnaire_results(self) -> list[QuestionnaireResult]:
        return [
            questionnaire_result
            for contribution_result in self.contribution_results
            for questionnaire_result in contribution_result.questionnaire_results
        ]


def get_single_result_rating_result(evaluation):
    assert evaluation.is_single_result

    answer_counters = RatingAnswerCounter.objects.filter(contribution__evaluation__pk=evaluation.pk)
    assert 1 <= len(answer_counters) <= 5

    question = Question.objects.get(questionnaire__name_en=Questionnaire.SINGLE_RESULT_QUESTIONNAIRE_NAME)
    return create_rating_result(question, answer_counters)


def get_results_cache_key(evaluation):
    return f"evap.staff.results.tools.get_results-{evaluation.id:d}"


def cache_results(evaluation, *, refetch_related_objects=True):
    assert evaluation.state in STATES_WITH_RESULTS_CACHING
    cache_key = get_results_cache_key(evaluation)
    caches["results"].set(cache_key, _get_results_impl(evaluation, refetch_related_objects=refetch_related_objects))


def get_results(evaluation):
    assert evaluation.state in STATES_WITH_RESULTS_CACHING | {Evaluation.State.IN_EVALUATION}

    if evaluation.state == Evaluation.State.IN_EVALUATION:
        return _get_results_impl(evaluation)

    cache_key = get_results_cache_key(evaluation)
    result = caches["results"].get(cache_key)
    assert result is not None
    return result


GET_RESULTS_PREFETCH_LOOKUPS = [
    "contributions__textanswer_set",
    "contributions__ratinganswercounter_set",
    "contributions__contributor__delegates",
    "contributions__questionnaires__questions",
    "course__responsibles__delegates",
]


def _get_results_impl(evaluation: Evaluation, *, refetch_related_objects: bool = True):
    if refetch_related_objects:
        discard_cached_related_objects(evaluation)

    prefetch_related_objects([evaluation], *GET_RESULTS_PREFETCH_LOOKUPS)

    tas_per_contribution_question: dict[tuple[int, int], list[TextAnswer]] = unordered_groupby(
        ((textanswer.contribution_id, textanswer.question_id), textanswer)
        for contribution in evaluation.contributions.all()
        for textanswer in contribution.textanswer_set.all()
        if textanswer.review_decision in [TextAnswer.ReviewDecision.PRIVATE, TextAnswer.ReviewDecision.PUBLIC]
    )

    racs_per_contribution_question: dict[tuple[int, int], list[RatingAnswerCounter]] = unordered_groupby(
        ((counter.contribution_id, counter.question_id), counter)
        for contribution in evaluation.contributions.all()
        for counter in contribution.ratinganswercounter_set.all()
    )

    contributor_contribution_results = []
    for contribution in evaluation.contributions.all():
        questionnaire_results = []
        for questionnaire in contribution.questionnaires.all():
            results: list[HeadingResult | TextResult | RatingResult] = []
            for question in questionnaire.questions.all():
                if question.is_heading_question:
                    results.append(HeadingResult(question=question))
                    continue
                text_result = None
                if question.can_have_textanswers and evaluation.can_publish_text_results:
                    answers = tas_per_contribution_question.get((contribution.id, question.id), [])
                    text_result = TextResult(
                        question=question, answers=answers, answers_visible_to=textanswers_visible_to(contribution)
                    )
                if question.is_rating_question:
                    if evaluation.can_publish_rating_results:
                        answer_counters = racs_per_contribution_question.get((contribution.id, question.id), [])
                    else:
                        answer_counters = None
                    results.append(create_rating_result(question, answer_counters, additional_text_result=text_result))
                elif question.is_text_question and evaluation.can_publish_text_results:
                    assert text_result is not None
                    results.append(text_result)

            questionnaire_results.append(QuestionnaireResult(questionnaire, results))
        contributor_contribution_results.append(
            ContributionResult(contribution.contributor, contribution.label, questionnaire_results)
        )
    return EvaluationResult(contributor_contribution_results)


def annotate_distributions_and_grades(evaluations):
    for evaluation in evaluations:
        if not evaluation.is_single_result:
            evaluation.distribution = calculate_average_distribution(evaluation)
        else:
            evaluation.single_result_rating_result = get_single_result_rating_result(evaluation)
            evaluation.distribution = normalized_distribution(evaluation.single_result_rating_result.counts)
        evaluation.avg_grade = distribution_to_grade(evaluation.distribution)


def normalized_distribution(distribution):
    """Returns a normalized distribution with the individual values adding up to 1.
    Can also be used to convert counts to a distribution."""
    if distribution is None:
        return None

    distribution_sum = sum(distribution)
    if distribution_sum == 0:
        return None

    return tuple((value / distribution_sum) for value in distribution)


def unipolarized_distribution(result):
    summed_distribution = [0, 0, 0, 0, 0]

    if not result.counts:
        return None

    for counts, grade in zip(result.counts, result.choices.grades):
        grade_fraction, grade = modf(grade)
        grade = int(grade)
        summed_distribution[grade - 1] += (1 - grade_fraction) * counts
        if grade < 5:
            summed_distribution[grade] += grade_fraction * counts

    return normalized_distribution(summed_distribution)


def avg_distribution(weighted_distributions):
    if all(distribution is None for distribution, __ in weighted_distributions):
        return None

    summed_distribution = [0, 0, 0, 0, 0]
    for distribution, weight in weighted_distributions:
        if distribution:
            for index, value in enumerate(distribution):
                summed_distribution[index] += weight * value
    return normalized_distribution(summed_distribution)


def average_grade_questions_distribution(results):
    return avg_distribution(
        [
            (unipolarized_distribution(result), result.count_sum)
            for result in results
            if result.question.is_grade_question
        ]
    )


def average_non_grade_rating_questions_distribution(results):
    return avg_distribution(
        [
            (unipolarized_distribution(result), result.count_sum)
            for result in results
            if result.question.is_non_grade_rating_question
        ]
    )


def calculate_average_course_distribution(course, check_for_unpublished_evaluations=True):
    if check_for_unpublished_evaluations and course.evaluations.exclude(state=Evaluation.State.PUBLISHED).exists():
        return None

    return avg_distribution(
        [
            (
                (
                    calculate_average_distribution(evaluation)
                    if not evaluation.is_single_result
                    else normalized_distribution(get_single_result_rating_result(evaluation).counts)
                ),
                evaluation.weight,
            )
            for evaluation in course.evaluations.all()
        ]
    )


def get_evaluations_with_course_result_attributes(evaluations):
    courses_with_unpublished_evaluations = (
        Course.objects.filter(evaluations__in=evaluations)
        .filter(Exists(Evaluation.objects.filter(course=OuterRef("pk")).exclude(state=Evaluation.State.PUBLISHED)))
        .values_list("id", flat=True)
    )

    course_id_evaluation_weight_sum_pairs = (
        Course.objects.annotate(Sum("evaluations__weight"))
        .filter(pk__in=Course.objects.filter(evaluations__in=evaluations))  # is needed, see #1691
        .values_list("id", "evaluations__weight__sum")
    )

    evaluation_weight_sum_per_course_id = {entry[0]: entry[1] for entry in course_id_evaluation_weight_sum_pairs}

    for evaluation in evaluations:
        if evaluation.course.id in courses_with_unpublished_evaluations:
            evaluation.course.not_all_evaluations_are_published = True
            evaluation.course.distribution = None
        else:
            evaluation.course.distribution = calculate_average_course_distribution(evaluation.course, False)

        evaluation.course.evaluation_count = evaluation.course.evaluations.count()
        evaluation.course.avg_grade = distribution_to_grade(evaluation.course.distribution)
        evaluation.course.evaluation_weight_sum = evaluation_weight_sum_per_course_id[evaluation.course.id]

    return evaluations


def calculate_average_distribution(evaluation):
    assert evaluation.state >= Evaluation.State.IN_EVALUATION

    if not evaluation.can_staff_see_average_grade or not evaluation.can_publish_average_grade:
        return None

    # will contain a list of question results for each contributor and one for the evaluation (where contributor is None)
    grouped_results = defaultdict(list)
    for contribution_result in get_results(evaluation).contribution_results:
        for questionnaire_result in contribution_result.questionnaire_results:
            grouped_results[contribution_result.contributor].extend(questionnaire_result.question_results)

    evaluation_results = grouped_results.pop(None, [])

    average_contributor_distribution = avg_distribution(
        [
            (
                avg_distribution(
                    [
                        (
                            average_grade_questions_distribution(contributor_results),
                            settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT,
                        ),
                        (
                            average_non_grade_rating_questions_distribution(contributor_results),
                            settings.CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT,
                        ),
                    ]
                ),
                max(
                    (result.count_sum for result in contributor_results if result.question.is_rating_question),
                    default=0,
                ),
            )
            for contributor_results in grouped_results.values()
        ]
    )

    return avg_distribution(
        [
            (average_grade_questions_distribution(evaluation_results), settings.GENERAL_GRADE_QUESTIONS_WEIGHT),
            (
                average_non_grade_rating_questions_distribution(evaluation_results),
                settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT,
            ),
            (average_contributor_distribution, settings.CONTRIBUTIONS_WEIGHT),
        ]
    )


def distribution_to_grade(distribution):
    if distribution is None:
        return None
    return sum(answer * percentage for answer, percentage in enumerate(distribution, start=1))


def color_mix(color1, color2, fraction):
    return cast(
        tuple[int, int, int], tuple(int(round(color1[i] * (1 - fraction) + color2[i] * fraction)) for i in range(3))
    )


def get_grade_color(grade):
    # Can happen if no one leaves any grades. Return white because it least likely causes problems.
    if not grade:
        return (255, 255, 255)
    grade = round(grade, 1)
    next_lower = int(grade)
    next_higher = int(ceil(grade))
    return color_mix(GRADE_COLORS[next_lower], GRADE_COLORS[next_higher], grade - next_lower)


def textanswers_visible_to(contribution):
    if contribution.is_general:
        contributors = {
            other_contribution.contributor
            for other_contribution in contribution.evaluation.contributions.all()
            if other_contribution.textanswer_visibility == Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS
        }
        contributors.update(contribution.evaluation.course.responsibles.all())
    else:
        contributors = {contribution.contributor}

    non_proxy_contributors = [contributor for contributor in contributors if not contributor.is_proxy_user]
    delegates = {delegate for contributor in non_proxy_contributors for delegate in contributor.delegates.all()}
    num_delegates = len(delegates - contributors)

    sorted_contributors = sorted(contributors, key=UserProfile.ordering_key)
    return TextAnswerVisibility(visible_by_contribution=sorted_contributors, visible_by_delegation_count=num_delegates)


def can_textanswer_be_seen_by(
    user: UserProfile,
    represented_users: list[UserProfile],
    textanswer: TextAnswer,
    view: str,
) -> bool:
    # pylint: disable=too-many-return-statements
    assert textanswer.review_decision in [TextAnswer.ReviewDecision.PRIVATE, TextAnswer.ReviewDecision.PUBLIC]
    contributor = textanswer.contribution.contributor

    if view == "public":
        return False

    if view == "export":
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
    if textanswer.is_public:
        # users can see textanswers if the contributor is one of their represented users (which includes the user itself)
        if contributor in represented_users:
            return True
        # users can see text answers from general contributions if one of their represented users has text answer
        # visibility GENERAL_TEXTANSWERS for the evaluation
        if (
            textanswer.contribution.is_general
            and textanswer.contribution.evaluation.contributions.filter(
                contributor__in=represented_users,
                textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            ).exists()
        ):
            return True
        # the people responsible for a course can see all general text answers for all its evaluations
        if textanswer.contribution.is_general and any(
            user in represented_users for user in textanswer.contribution.evaluation.course.responsibles.all()
        ):
            return True

    return False
