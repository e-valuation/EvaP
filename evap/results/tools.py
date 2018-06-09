from collections import namedtuple, defaultdict
from functools import partial
from math import ceil
from statistics import median
import itertools

from django.conf import settings
from django.core.cache import caches
from django.db.models import Sum

from evap.evaluation.models import TextAnswer, Contribution, RatingAnswerCounter
from evap.evaluation.tools import questionnaires_and_contributions


GRADE_COLORS = {
    1: (136, 191, 74),
    2: (187, 209, 84),
    3: (239, 226, 88),
    4: (242, 158, 88),
    5: (235,  89, 90),
}


# see calculate_results
ResultSection = namedtuple('ResultSection', ('questionnaire', 'contributor', 'label', 'results', 'warning'))
CommentSection = namedtuple('CommentSection', ('questionnaire', 'contributor', 'label', 'is_responsible', 'results'))
HeadingResult = namedtuple('HeadingResult', ('question'))

class RatingResult:
    def __init__(self, question, counts, warning):
        assert question.is_rating_question
        self.question = question
        self.counts = counts
        self.warning = warning

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


def get_answers(contribution, question):
    return question.answer_class.objects.filter(contribution=contribution, question=question)


def get_textanswers(contribution, question, filter_states=None):
    assert question.is_text_question
    answers = get_answers(contribution, question)
    if filter_states is not None:
        answers = answers.filter(state__in=filter_states)
    return answers


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
    """Calculates the result data for a single course. Returns a list of
    `ResultSection` tuples. Each of those tuples contains the questionnaire, the
    contributor (or None), a list of (Rating|Text|Heading)Result tuples,
    the average grade and distribution for that section (or None)."""

    # there will be one section per relevant questionnaire--contributor pair
    sections = []

    # calculate the median values of how many people answered a questionnaire type (lecturer, tutor, ...)
    questionnaire_med_answers = defaultdict(list)
    questionnaire_max_answers = {}
    questionnaire_warning_thresholds = {}
    for questionnaire, contribution in questionnaires_and_contributions(course):
        max_answers = max([get_answers(contribution, question).aggregate(Sum('count'))['count__sum'] or 0 for question in questionnaire.rating_questions], default=0)
        questionnaire_max_answers[(questionnaire, contribution)] = max_answers
        questionnaire_med_answers[questionnaire].append(max_answers)
    for questionnaire, max_answers in questionnaire_med_answers.items():
        questionnaire_warning_thresholds[questionnaire] = max(settings.RESULTS_WARNING_PERCENTAGE * median(max_answers), settings.RESULTS_WARNING_COUNT)

    for questionnaire, contribution in questionnaires_and_contributions(course):
        results_contain_rating_questions = False
        # will contain one object per question
        results = []
        for question in questionnaire.question_set.all():
            if question.is_rating_question:
                results_contain_rating_questions = True
                counts = get_counts(get_answers(contribution, question)) if course.can_publish_rating_results else None
                warning = counts is not None and sum(counts) < questionnaire_warning_thresholds[questionnaire]
                results.append(RatingResult(question, counts, warning))
            elif question.is_text_question and course.can_publish_text_results:
                answers = get_textanswers(contribution, question, filter_states=[TextAnswer.PRIVATE, TextAnswer.PUBLISHED])
                results.append(TextResult(question=question, answers=answers))
            elif question.is_heading_question:
                results.append(HeadingResult(question=question))

        section_warning = 0 < questionnaire_max_answers[(questionnaire, contribution)] < questionnaire_warning_thresholds[questionnaire] and results_contain_rating_questions

        sections.append(ResultSection(questionnaire, contribution.contributor, contribution.label, results, section_warning))

    return sections


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

    # will contain a list of results for each contributor and one for the course (where contributor is None)
    grouped_results = defaultdict(list)
    for __, contributor, __, results, __ in calculate_results(course):
        grouped_results[contributor].extend(results)

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


def has_no_rating_answers(course, contributor, questionnaire):
    questions = questionnaire.rating_questions
    contribution = Contribution.objects.get(course=course, contributor=contributor)
    return RatingAnswerCounter.objects.filter(question__in=questions, contribution=contribution).count() == 0


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
