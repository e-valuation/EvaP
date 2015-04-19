from django.conf import settings
from django.core.cache import cache
from django.utils.translation import ugettext_lazy as _
from evap.evaluation.models import TextAnswer

from collections import OrderedDict, defaultdict
from collections import namedtuple
from math import ceil

GRADE_COLORS = {
    1: (136, 191, 74),
    2: (187, 209, 84),
    3: (239, 226, 88),
    4: (242, 158, 88),
    5: (235,  89, 90),
}

LIKERT_NAMES = {
    1: _("Strongly agree"),
    2: _("Agree"),
    3: _("Neither agree nor disagree"),
    4: _("Disagree"),
    5: _("Strongly disagree"),
    6: _("no answer"),
}

GRADE_NAMES = {
    1: _("1"),
    2: _("2"),
    3: _("3"),
    4: _("4"),
    5: _("5"),
    6: _("no answer"),
}

# the names used for contributors and staff
STATES_ORDERED = OrderedDict((
    ('new', _('new')),
    ('prepared', _('prepared')),
    ('lecturerApproved', _('lecturer approved')),
    ('approved', _('approved')),
    ('inEvaluation', _('in evaluation')),
    ('evaluated', _('evaluated')),
    ('reviewed', _('reviewed')),
    ('published', _('published'))
))

# the descriptions used in tooltips for contributors
STATE_DESCRIPTIONS = OrderedDict((
    ('new', _('The course was newly created and will be prepared by the student representatives.')),
    ('prepared', _('The course was prepared by the student representatives and is now available for editing to the responsible person.')),
    ('lecturerApproved', _('The course was approved by the responsible person and will now be checked by the student representatives.')),
    ('approved', _('All preparations are finished. The evaluation will begin once the defined start date is reached.')),
    ('inEvaluation', _('The course is currently in evaluation until the defined end date is reached.')),
    ('evaluated', _('The course was fully evaluated and will now be reviewed by the student representatives.')),
    ('reviewed', _('The course was fully evaluated and reviewed by the student representatives. You will receive an email when its results are published.')),
    ('published', _('The results for this course have been published.'))
))

# the names used for students
STUDENT_STATES_ORDERED = OrderedDict((
    ('inEvaluation', _('in evaluation')),
    ('upcoming', _('upcoming')),
    ('evaluationFinished', _('evaluation finished')),
    ('published', _('published'))
))

# see calculate_results
ResultSection = namedtuple('ResultSection', ('questionnaire', 'contributor', 'results', 'warning'))
CommentSection = namedtuple('CommentSection', ('questionnaire', 'contributor', 'is_responsible', 'results'))
RatingResult = namedtuple('RatingResult', ('question', 'count', 'average', 'variance', 'distribution', 'warning'))
TextResult = namedtuple('TextResult', ('question', 'answers'))

def avg(iterable):
    """Simple arithmetic average function. Returns `None` if the length of
    `iterable` is 0 or no items except None exist."""
    items = [item for item in iterable if item is not None]
    if len(items) == 0:
        return None
    return float(sum(items)) / len(items)


def med(iterable):
    """Simple arithmetic median function. Returns `None` if the length of
    `iterable` is 0 or no items except None exist."""
    items = [item for item in iterable if item is not None]
    length = len(items)
    if length == 0:
        return None
    sorted_items = sorted(items)
    index = int(length / 2)
    if length % 2 == 0:
        return (sorted_items[index] + sorted_items[index]) / 2.0
    return sorted_items[index]


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


def get_textanswers(contribution, question, filter_states=None):
    assert question.is_text_question
    answers = get_answers(contribution, question)
    if filter_states is not None:
        answers = answers.filter(state__in=filter_states)
    return answers


def get_distribution(answers):
    count = len(answers)
    if count == 0:
        return None
    distribution = OrderedDict()
    for i in range(1, 6):
        distribution[i] = 0
    for answer in answers:
        distribution[answer] += 1
    # divide by the number of answers to get relative 0..1 values
    for k in distribution:
        distribution[k] = float(distribution[k]) / count * 100.0
    return distribution


def calculate_results(course):
    if course.state == "published":
        cache_key = str.format('evap.staff.results.tools.calculate_results-{:d}', course.id)
        prior_results = cache.get(cache_key)
        if prior_results:
            return prior_results

    results = _calculate_results_impl(course)

    if course.state == "published":
        cache.set(cache_key, results, None)
    return results


def _calculate_results_impl(course):
    """Calculates the result data for a single course. Returns a list of
    `ResultSection` tuples. Each of those tuples contains the questionnaire, the
    contributor (or None), a list of single result elements, the average grade and
    variance for that section (or None). The result elements are either
    `RatingResult` or `TextResult` instances."""

    # there will be one section per relevant questionnaire--contributor pair
    sections = []

    # calculate the median values of how many people answered a questionnaire type (lecturer, tutor, ...)
    questionnaire_med_answers = defaultdict(list)
    questionnaire_max_answers = {}
    questionnaire_warning_thresholds = {}
    for questionnaire, contribution in questionnaires_and_contributions(course):
        max_answers = max([get_answers(contribution, question).count() for question in questionnaire.rating_questions], default=0)
        questionnaire_max_answers[(questionnaire, contribution)] = max_answers
        questionnaire_med_answers[questionnaire].append(max_answers)
    for questionnaire, max_answers in questionnaire_med_answers.items():
        questionnaire_warning_thresholds[questionnaire] = settings.RESULTS_WARNING_PERCENTAGE * med(max_answers)

    for questionnaire, contribution in questionnaires_and_contributions(course):
        # will contain one object per question
        results = []
        for question in questionnaire.question_set.all():
            if question.is_rating_question:
                answers = get_answers(contribution, question).values_list('answer', flat=True)

                count = len(answers)
                average = avg(answers)
                variance = avg((average - answer) ** 2 for answer in answers)
                distribution = get_distribution(answers)
                warning = count > 0 and count < questionnaire_warning_thresholds[questionnaire]

                results.append(RatingResult(question, count, average, variance, distribution, warning))

            elif question.is_text_question:
                allowed_states = [TextAnswer.PRIVATE, TextAnswer.PUBLISHED]
                answers = get_textanswers(contribution, question, allowed_states)
                results.append(TextResult(question=question, answers=answers))

        section_warning = questionnaire_max_answers[(questionnaire, contribution)] < questionnaire_warning_thresholds[questionnaire]

        sections.append(ResultSection(questionnaire, contribution.contributor, results, section_warning))

    return sections


def calculate_average_grades_and_variance(course):
    """Determines the final average grade and variance for a course."""
    avg_generic_likert = []
    avg_contribution_likert = []
    var_generic_likert = []
    var_contribution_likert = []
    avg_generic_grade = []
    avg_contribution_grade = []
    var_generic_grade = []
    var_contribution_grade = []

    for questionnaire, contributor, results, warning in calculate_results(course):
        average_likert = avg([result.average for result in results if result.question.is_likert_question])
        variance_likert = avg([result.variance for result in results if result.question.is_likert_question])
        average_grade = avg([result.average for result in results if result.question.is_grade_question])
        variance_grade = avg([result.variance for result in results if result.question.is_grade_question])

        (avg_contribution_likert if contributor else avg_generic_likert).append(average_likert)
        (var_contribution_likert if contributor else var_generic_likert).append(variance_likert)
        (avg_contribution_grade if contributor else avg_generic_grade).append(average_grade)
        (var_contribution_grade if contributor else var_generic_grade).append(variance_grade)

    # the final total grade will be calculated by the following formula (GP = GRADE_PERCENTAGE, CP = CONTRIBUTION_PERCENTAGE):
    # final_likert = CP * likert_answers_about_persons + (1-CP) * likert_answers_about_courses
    # final_grade = CP * grade_answers_about_persons + (1-CP) * grade_answers_about_courses
    # final = GP * final_grade + (1-GP) * final_likert

    final_likert_avg = mix(avg(avg_contribution_likert), avg(avg_generic_likert), settings.CONTRIBUTION_PERCENTAGE)
    final_likert_var = mix(avg(var_contribution_likert), avg(var_generic_likert), settings.CONTRIBUTION_PERCENTAGE)
    final_grade_avg = mix(avg(avg_contribution_grade), avg(avg_generic_grade), settings.CONTRIBUTION_PERCENTAGE)
    final_grade_var = mix(avg(var_contribution_grade), avg(var_generic_grade), settings.CONTRIBUTION_PERCENTAGE)

    final_avg = mix(final_grade_avg, final_likert_avg, settings.GRADE_PERCENTAGE)
    final_var = mix(final_grade_var, final_likert_var, settings.GRADE_PERCENTAGE)

    return final_avg, final_var


def questionnaires_and_contributions(course):
    """Yields tuples of (questionnaire, contribution) for the given course."""
    result = []

    for contribution in course.contributions.all():
        for questionnaire in contribution.questionnaires.all():
            result.append((questionnaire, contribution))

    # sort questionnaires for general contributions first
    result.sort(key=lambda t: not t[1].is_general)

    return result


def is_external_email(email):
    return not any([email.endswith("@" + domain) for domain in settings.INSTITUTION_EMAIL_DOMAINS])


def user_publish_notifications(courses):
    user_notifications = defaultdict(set)
    for course in courses:
        # for published courses all contributors and participants get a notification
        if course.can_publish_grades:
            for participant in course.participants.all():
                user_notifications[participant].add(course)
            for contribution in course.contributions.all():
                if contribution.contributor:
                    user_notifications[contribution.contributor].add(course)
        # if a course was not published notifications are only sent for contributors who can see comments
        elif len(course.textanswer_set) > 0:
            for textanswer in course.textanswer_set:
                if textanswer.contribution.contributor:
                    user_notifications[textanswer.contribution.contributor].add(course)
            user_notifications[course.responsible_contributor].add(course)

    return user_notifications

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

def get_variance_color(variance):
    if variance is None:
        return (255, 255, 255)

    val = int(255 - variance * 70) # tweaked to look good
    return (val, val, val)

