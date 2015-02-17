from django.conf import settings
from django.core.cache import cache
from django.utils.translation import ugettext_lazy as _
from evap.evaluation.models import LikertAnswer, TextAnswer, GradeAnswer

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

# the names used for students
STUDENT_STATES_ORDERED = OrderedDict((
    ('inEvaluation', _('in evaluation')),
    ('upcoming', _('upcoming')),
    ('evaluationFinished', _('evaluation finished')),
    ('published', _('published'))
))

# see calculate_results
ResultSection = namedtuple('ResultSection', ('questionnaire', 'contributor', 'results', 'average_likert', 'median_likert', 'average_grade', 'median_grade', 'average_total', 'median_total', 'warning'))
CommentSection = namedtuple('CommentSection', ('questionnaire', 'contributor', 'is_responsible', 'results'))
LikertResult = namedtuple('LikertResult', ('question', 'count', 'average', 'median', 'variance', 'distribution', 'show', 'warning'))
TextResult = namedtuple('TextResult', ('question', 'answers'))
GradeResult = namedtuple('GradeResult', ('question', 'count', 'average', 'median', 'variance', 'distribution', 'show', 'warning'))


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


def get_all_textanswers(course, contribution, question):
    return get_answers(course, contribution, question, exclusion=[])


def get_answers(course, contribution, question, exclusion=['', 'N']):
    answers = None

    if question.is_likert_question:
        answers = LikertAnswer.objects.filter(
            contribution__course=course,
            contribution__contributor=contribution.contributor,
            question=question
            ).values_list('answer', flat=True)

    elif question.is_grade_question:
        answers = GradeAnswer.objects.filter(
            contribution__course=course,
            contribution__contributor=contribution.contributor,
            question=question
            ).values_list('answer', flat=True)

    elif question.is_text_question:
        answers = TextAnswer.objects.filter(
            contribution__course=course,
            contribution__contributor=contribution.contributor,
            question=question,
        ).exclude(state__in=exclusion)

    return answers


def calculate_results(course, staff_member=False):
    """Calculates the result data for a single course. Returns a list of
    `ResultSection` tuples. Each of those tuples contains the questionnaire, the
    contributor (or None), a list of single result elements, the average and
    median grades for that section (or None). The result elements are either
    `LikertResult`, `TextResult` or `GradeResult` instances."""

    # return cached results if available
    cache_key = str.format('evap.staff.results.views.calculate_results-{:d}-{:d}', course.id, staff_member)
    prior_results = cache.get(cache_key)
    if prior_results:
        return prior_results

    # check if grades for the course will be published
    show = staff_member or course.can_publish_grades

    # there will be one section per relevant questionnaire--contributor pair
    sections = []

    # calculate the median values of how many people answered a questionnaire type (lecturer, tutor, ...)
    questionnaire_med_answers = {}
    questionnaire_max_answers = {}
    for questionnaire, contribution in questionnaires_and_contributions(course):
        if questionnaire not in questionnaire_med_answers:
            questionnaire_med_answers[questionnaire] = []
        max_answers = 0
        for question in questionnaire.question_set.all():
            # don't count text questions, because few answers here should not result in warnings and having a median of 0 prevents a warning
            if not question.is_text_question:
                answers = get_answers(course, contribution, question)
                if len(answers) > max_answers:
                    max_answers = len(answers)
        questionnaire_max_answers[(questionnaire, contribution)] = max_answers
        questionnaire_med_answers[questionnaire].append(max_answers)
    for questionnaire in questionnaire_med_answers:
        questionnaire_med_answers[questionnaire] = med(questionnaire_med_answers[questionnaire])

    for questionnaire, contribution in questionnaires_and_contributions(course):
        # will contain one object per question
        results = []
        for question in questionnaire.question_set.all():
            if question.is_likert_question or question.is_grade_question:
                answers = get_answers(course, contribution, question)

                # calculate average, median and distribution
                if answers:
                    # average
                    average = avg(answers)
                    # median
                    median = med(answers)
                    # variance
                    variance = avg((average - answer) ** 2 for answer in answers)
                    # calculate relative distribution (histogram) of answers:
                    # set up a sorted dictionary with a count of zero for each grade
                    distribution = OrderedDict()
                    for i in range(1, 6):
                        distribution[i] = 0
                    # count the answers
                    for answer in answers:
                        distribution[answer] += 1
                    # divide by the number of answers to get relative 0..1 values
                    for k in distribution:
                        distribution[k] = float(distribution[k]) / len(answers) * 100.0
                else:
                    average = None
                    median = None
                    variance = None
                    distribution = None

                warning = len(answers) > 0 and len(answers) < settings.RESULTS_WARNING_PERCENTAGE * questionnaire_med_answers[questionnaire]
                # produce the result element
                kwargs = {
                    'question': question,
                    'count': len(answers),
                    'average': average,
                    'median': median,
                    'variance': variance,
                    'distribution': distribution,
                    'show': show,
                    'warning': warning
                }
                if question.is_likert_question:
                    results.append(LikertResult(**kwargs))
                elif question.is_grade_question:
                    results.append(GradeResult(**kwargs))
            elif question.is_text_question:
                answers = get_answers(course, contribution, question)

                # only add to the results if answers exist at all
                if answers:
                    results.append(TextResult(
                        question=question,
                        answers=[answer for answer in answers]
                    ))

        # skip section if there were no questions with results
        if not results:
            continue

        # compute average and median grades for all LikertResults in this
        # section, will return None if no LikertResults exist in this section
        average_likert = avg([result.average for result in results if isinstance(result, LikertResult)])
        median_likert = med([result.median for result in results if isinstance(result, LikertResult)])

        # compute average and median grades for all GradeResults in this
        # section, will return None if no GradeResults exist in this section
        average_grade = avg([result.average for result in results if isinstance(result, GradeResult)])
        median_grade = med([result.median for result in results if isinstance(result, GradeResult)])

        average_total = mix(average_grade, average_likert, settings.GRADE_PERCENTAGE)
        median_total = mix(median_grade, median_likert, settings.GRADE_PERCENTAGE)

        max_answers_this_questionnaire = questionnaire_max_answers[(questionnaire, contribution)]
        med_answers_this_questionnaire_type = questionnaire_med_answers[questionnaire]
        warning_threshold = settings.RESULTS_WARNING_PERCENTAGE * med_answers_this_questionnaire_type
        section_warning = med_answers_this_questionnaire_type > 0 and max_answers_this_questionnaire < warning_threshold

        sections.append(ResultSection(
            questionnaire, contribution.contributor, results,
            average_likert, median_likert,
            average_grade, median_grade,
            average_total, median_total,
            section_warning))

    # store results into cache
    # XXX: What would be a good timeout here? Once public, data is not going to
    #      change anyway.
    cache.set(cache_key, sections, 24 * 60 * 60)

    return sections


def calculate_average_and_medium_grades(course):
    """Determines the final average and median grades for a course."""
    avg_generic_likert = []
    avg_contribution_likert = []
    med_generic_likert = []
    med_contribution_likert = []
    avg_generic_grade = []
    avg_contribution_grade = []
    med_generic_grade = []
    med_contribution_grade = []

    for questionnaire, contributor, results, average_likert, median_likert, average_grade, median_grade, average_total, median_total, warning in calculate_results(course):
        if average_likert:
            (avg_contribution_likert if contributor else avg_generic_likert).append(average_likert)
        if median_likert:
            (med_contribution_likert if contributor else med_generic_likert).append(median_likert)
        if average_grade:
            (avg_contribution_grade if contributor else avg_generic_grade).append(average_grade)
        if median_grade:
            (med_contribution_grade if contributor else med_generic_grade).append(median_grade)

    # the final total grade will be calculated by the following formula (GP = GRADE_PERCENTAGE, CP = CONTRIBUTION_PERCENTAGE):
    # final_likert = CP * likert_answers_about_persons + (1-CP) * likert_answers_about_courses
    # final_grade = CP * grade_answers_about_persons + (1-CP) * grade_answers_about_courses
    # final = GP * final_grade + (1-GP) * final_likert

    final_likert_avg = mix(avg(avg_contribution_likert), avg(avg_generic_likert), settings.CONTRIBUTION_PERCENTAGE)
    final_likert_med = mix(med(med_contribution_likert), med(med_generic_likert), settings.CONTRIBUTION_PERCENTAGE)
    final_grade_avg = mix(avg(avg_contribution_grade), avg(avg_generic_grade), settings.CONTRIBUTION_PERCENTAGE)
    final_grade_med = mix(med(med_contribution_grade), med(med_generic_grade), settings.CONTRIBUTION_PERCENTAGE)

    final_avg = mix(final_grade_avg, final_likert_avg, settings.GRADE_PERCENTAGE)
    final_med = mix(final_grade_med, final_likert_med, settings.GRADE_PERCENTAGE)

    return final_avg, final_med


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
