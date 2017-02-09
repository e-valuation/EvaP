from collections import namedtuple, defaultdict, OrderedDict
from functools import partial
from math import ceil
from statistics import pstdev, median

from django.conf import settings
from django.core.cache import cache
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
RatingResult = namedtuple('RatingResult', ('question', 'total_count', 'average', 'deviation', 'counts', 'warning'))
TextResult = namedtuple('TextResult', ('question', 'answers'))


def avg(iterable):
    """Simple arithmetic average function. Returns `None` if the length of
    `iterable` is 0 or no items except None exist."""
    items = [item for item in iterable if item is not None]
    if len(items) == 0:
        return None
    return float(sum(items)) / len(items)


def mix(a, b, alpha):
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a

    return alpha * a + (1 - alpha) * b


def get_answers(contribution, question):
    return question.answer_class.objects.filter(contribution=contribution, question=question)


def get_number_of_answers(contribution, question):
    answers = get_answers(contribution, question)
    if question.is_rating_question:
        return get_sum_of_answer_counters(answers)
    else:
        return len(answers)


def get_sum_of_answer_counters(answer_counters):
    return answer_counters.aggregate(total_count=Sum('count'))['total_count'] or 0


def get_answers_from_answer_counters(answer_counters):
    answers = []
    for answer_counter in answer_counters:
        for __ in range(0, answer_counter.count):
            answers.append(answer_counter.answer)
    return answers


def get_textanswers(contribution, question, filter_states=None):
    assert question.is_text_question
    answers = get_answers(contribution, question)
    if filter_states is not None:
        answers = answers.filter(state__in=filter_states)
    return answers


def get_counts(answer_counters):
    counts = OrderedDict()
    # ensure ordering of answers
    for answer in range(1, 6):
        counts[answer] = 0

    for answer_counter in answer_counters:
        counts[answer_counter.answer] = answer_counter.count
    return counts


def calculate_results(course, force_recalculation=False):
    if course.state != "published":
        return _calculate_results_impl(course)

    cache_key = 'evap.staff.results.tools.calculate_results-{:d}'.format(course.id)
    if force_recalculation:
        cache.delete(cache_key)
    return cache.get_or_set(cache_key, partial(_calculate_results_impl, course), None)


def _calculate_results_impl(course):
    """Calculates the result data for a single course. Returns a list of
    `ResultSection` tuples. Each of those tuples contains the questionnaire, the
    contributor (or None), a list of single result elements, the average grade and
    deviation for that section (or None). The result elements are either
    `RatingResult` or `TextResult` instances."""

    # there will be one section per relevant questionnaire--contributor pair
    sections = []

    # calculate the median values of how many people answered a questionnaire type (lecturer, tutor, ...)
    questionnaire_med_answers = defaultdict(list)
    questionnaire_max_answers = {}
    questionnaire_warning_thresholds = {}
    for questionnaire, contribution in questionnaires_and_contributions(course):
        max_answers = max([get_number_of_answers(contribution, question) for question in questionnaire.rating_questions], default=0)
        questionnaire_max_answers[(questionnaire, contribution)] = max_answers
        questionnaire_med_answers[questionnaire].append(max_answers)
    for questionnaire, max_answers in questionnaire_med_answers.items():
        questionnaire_warning_thresholds[questionnaire] = settings.RESULTS_WARNING_PERCENTAGE * median(max_answers)

    for questionnaire, contribution in questionnaires_and_contributions(course):
        # will contain one object per question
        results = []
        for question in questionnaire.question_set.all():
            if question.is_rating_question:
                answer_counters = get_answers(contribution, question)
                answers = get_answers_from_answer_counters(answer_counters)

                total_count = len(answers)
                average = avg(answers) if total_count > 0 else None
                deviation = pstdev(answers, average) if total_count > 0 else None
                counts = get_counts(answer_counters)
                warning = total_count > 0 and total_count < questionnaire_warning_thresholds[questionnaire]

                results.append(RatingResult(question, total_count, average, deviation, counts, warning))

            elif question.is_text_question:
                allowed_states = [TextAnswer.PRIVATE, TextAnswer.PUBLISHED]
                answers = get_textanswers(contribution, question, allowed_states)
                results.append(TextResult(question=question, answers=answers))

        section_warning = questionnaire_max_answers[(questionnaire, contribution)] < questionnaire_warning_thresholds[questionnaire]

        sections.append(ResultSection(questionnaire, contribution.contributor, contribution.label, results, section_warning))

    return sections


def calculate_average_grades_and_deviation(course):
    """Determines the final average grade and deviation for a course."""
    avg_generic_likert = []
    avg_contribution_likert = []
    dev_generic_likert = []
    dev_contribution_likert = []
    avg_generic_grade = []
    avg_contribution_grade = []
    dev_generic_grade = []
    dev_contribution_grade = []

    for __, contributor, __, results, __ in calculate_results(course):
        average_likert = avg([result.average for result in results if result.question.is_likert_question])
        deviation_likert = avg([result.deviation for result in results if result.question.is_likert_question])
        average_grade = avg([result.average for result in results if result.question.is_grade_question])
        deviation_grade = avg([result.deviation for result in results if result.question.is_grade_question])

        (avg_contribution_likert if contributor else avg_generic_likert).append(average_likert)
        (dev_contribution_likert if contributor else dev_generic_likert).append(deviation_likert)
        (avg_contribution_grade if contributor else avg_generic_grade).append(average_grade)
        (dev_contribution_grade if contributor else dev_generic_grade).append(deviation_grade)

    # the final total grade will be calculated by the following formula (GP = GRADE_PERCENTAGE, CP = CONTRIBUTION_PERCENTAGE):
    # final_likert = CP * likert_answers_about_persons + (1-CP) * likert_answers_about_courses
    # final_grade = CP * grade_answers_about_persons + (1-CP) * grade_answers_about_courses
    # final = GP * final_grade + (1-GP) * final_likert

    final_likert_avg = mix(avg(avg_contribution_likert), avg(avg_generic_likert), settings.CONTRIBUTION_PERCENTAGE)
    final_likert_dev = mix(avg(dev_contribution_likert), avg(dev_generic_likert), settings.CONTRIBUTION_PERCENTAGE)
    final_grade_avg = mix(avg(avg_contribution_grade), avg(avg_generic_grade), settings.CONTRIBUTION_PERCENTAGE)
    final_grade_dev = mix(avg(dev_contribution_grade), avg(dev_generic_grade), settings.CONTRIBUTION_PERCENTAGE)

    final_avg = mix(final_grade_avg, final_likert_avg, settings.GRADE_PERCENTAGE)
    final_dev = mix(final_grade_dev, final_likert_dev, settings.GRADE_PERCENTAGE)

    return final_avg, final_dev


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


def get_deviation_color(deviation):
    if deviation is None:
        return (255, 255, 255)

    capped_deviation = min(deviation, 2.0)  # values above that are very uncommon in practice
    val = int(255 - capped_deviation * 60)  # tweaked to look good
    return (val, val, val)
