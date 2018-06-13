from collections import namedtuple, defaultdict
from functools import partial
from math import ceil
import itertools

from django.conf import settings
from django.core.cache import caches

from evap.evaluation.models import TextAnswer, RatingAnswerCounter


GRADE_COLORS = {
    1: (136, 191, 74),
    2: (187, 209, 84),
    3: (239, 226, 88),
    4: (242, 158, 88),
    5: (235,  89, 90),
}


class CourseResult:
    def __init__(self, contribution_results):
        self.contribution_results = contribution_results

    @property
    def questionnaire_results(self):
        return [questionnaire_result for contribution_result in self.contribution_results for questionnaire_result in contribution_result.questionnaire_results]


class ContributionResult:
    def __init__(self, contributor, label, questionnaire_results):
        self.contributor = contributor
        self.label = label
        self.questionnaire_results = questionnaire_results

    @property
    def has_answers(self):
        for questionnaire_result in self.questionnaire_results:
            for question_result in questionnaire_result.question_results:
                question = question_result.question
                if question.is_text_question or question.is_rating_question and question_result.has_answers:
                    return True
        return False


class QuestionnaireResult:
    def __init__(self, questionnaire, question_results):
        self.questionnaire = questionnaire
        self.question_results = question_results


class RatingResult:
    def __init__(self, question, counts):
        assert question.is_rating_question
        self.question = question
        self.counts = counts

    @property
    def total_count(self):
        if not self.has_answers:
            return 0
        return sum(self.counts)

    @property
    def approval_count(self):
        assert self.question.is_yes_no_question
        if not self.has_answers:
            return None
        return self.counts[0] if self.question.is_positive_yes_no_question else self.counts[4]

    @property
    def average(self):
        if not self.has_answers:
            return None
        return sum(answer * count for answer, count in enumerate(self.counts, start=1)) / self.total_count

    @property
    def has_answers(self):
        return self.counts is not None


class TextResult:
    def __init__(self, question, answers):
        assert question.is_text_question
        self.question = question
        self.answers = answers


HeadingResult = namedtuple('HeadingResult', ('question'))


def get_answers(contribution, question):
    return question.answer_class.objects.filter(contribution=contribution, question=question)


def get_counts(answer_counters):
    if not answer_counters:
        return None

    counts = [0, 0, 0, 0, 0]
    for answer_counter in answer_counters:
        counts[answer_counter.answer - 1] = answer_counter.count
    return tuple(counts)


def get_results_cache_key(course):
    return 'evap.staff.results.tools.calculate_results-{:d}'.format(course.id)


def calculate_results(course, force_recalculation=False):
    if course.state != "published":
        return _calculate_results_impl(course)

    cache_key = get_results_cache_key(course)
    if force_recalculation:
        caches['results'].delete(cache_key)
    return caches['results'].get_or_set(cache_key, partial(_calculate_results_impl, course))


def _calculate_results_impl(course):
    contributor_contribution_results = []
    for contribution in course.contributions.all().prefetch_related("questionnaires", "questionnaires__question_set"):
        questionnaire_results = []
        for questionnaire in contribution.questionnaires.all():
            results = []
            for question in questionnaire.question_set.all():
                if question.is_rating_question:
                    counts = get_counts(get_answers(contribution, question)) if course.can_publish_rating_results else None
                    results.append(RatingResult(question, counts))
                elif question.is_text_question and course.can_publish_text_results:
                    answers = TextAnswer.objects.filter(contribution=contribution, question=question, state__in=[TextAnswer.PRIVATE, TextAnswer.PUBLISHED])
                    results.append(TextResult(question=question, answers=answers))
                elif question.is_heading_question:
                    results.append(HeadingResult(question=question))
            questionnaire_results.append(QuestionnaireResult(questionnaire, results))
        contributor_contribution_results.append(ContributionResult(contribution.contributor, contribution.label, questionnaire_results))
    return CourseResult(contributor_contribution_results)


def normalized_distribution(distribution):
    """Returns a normalized distribution with the individual values adding up to 1.
    Can also be used to convert counts to a distribution."""
    if distribution is None:
        return None

    distribution_sum = sum(distribution)
    return tuple((value / distribution_sum) for value in distribution)


def avg_distribution(distributions, weights=itertools.repeat(1)):
    if all(distribution is None for distribution in distributions):
        return None

    summed_distribution = [0, 0, 0, 0, 0]
    for distribution, weight in zip(distributions, weights):
        if distribution:
            for index, value in enumerate(distribution):
                summed_distribution[index] += weight * value
    return normalized_distribution(summed_distribution)


def average_grade_questions_distribution(results):
    return avg_distribution([normalized_distribution(result.counts) for result in results if result.question.is_grade_question])


def average_non_grade_rating_questions_distribution(results):
    return avg_distribution([normalized_distribution(result.counts) for result in results if result.question.is_non_grade_rating_question])


def calculate_average_distribution(course):
    if not course.can_publish_average_grade:
        return None

    # will contain a list of question results for each contributor and one for the course (where contributor is None)
    grouped_results = defaultdict(list)
    for contribution_result in calculate_results(course).contribution_results:
        for questionnaire_result in contribution_result.questionnaire_results:
            grouped_results[contribution_result.contributor].extend(questionnaire_result.question_results)

    course_results = grouped_results.pop(None, [])

    average_contributor_distribution = avg_distribution([
        avg_distribution(
            [average_grade_questions_distribution(results), average_non_grade_rating_questions_distribution(results)],
            [settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT, settings.CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT]
        ) for results in grouped_results.values()
    ])

    return avg_distribution(
        [average_grade_questions_distribution(course_results), average_non_grade_rating_questions_distribution(course_results), average_contributor_distribution],
        [settings.COURSE_GRADE_QUESTIONS_WEIGHT, settings.COURSE_NON_GRADE_QUESTIONS_WEIGHT, settings.CONTRIBUTIONS_WEIGHT]
    )


def distribution_to_grade(distribution):
    if distribution is None:
        return None
    return sum(answer * percentage for answer, percentage in enumerate(distribution, start=1))


def color_mix(color1, color2, fraction):
    return tuple(
        int(round(color1[i] * (1 - fraction) + color2[i] * fraction)) for i in range(3)
    )


def get_grade_color(grade):
    # Can happen if no one leaves any grades. Return white because its least likely to cause problems.
    if grade is None:
        return (255, 255, 255)
    grade = round(grade, 1)
    next_lower = int(grade)
    next_higher = int(ceil(grade))
    return color_mix(GRADE_COLORS[next_lower], GRADE_COLORS[next_higher], grade - next_lower)
