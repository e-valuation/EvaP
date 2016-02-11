from django.conf import settings
from django.core.cache import cache
from django.utils.translation import ugettext_lazy as _
from django.db.models import Sum
from evap.evaluation.models import TextAnswer, EmailTemplate, Course, Contribution, RatingAnswerCounter

from collections import OrderedDict, defaultdict
from collections import namedtuple
from functools import partial
from math import ceil
from statistics import pstdev, median

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
    ('editorApproved', _('lecturer approved')),
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
    ('editorApproved', _('The course was approved by a lecturer and will now be checked by the student representatives.')),
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
ResultSection = namedtuple('ResultSection', ('questionnaire', 'contributor', 'label', 'results', 'warning'))
CommentSection = namedtuple('CommentSection', ('questionnaire', 'contributor', 'is_responsible', 'results'))
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
        for i in range(0, answer_counter.count):
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
    for answer in range(1,6):
        counts[answer] = 0

    for answer_counter in answer_counters:
        counts[answer_counter.answer] = answer_counter.count
    return counts


def calculate_results(course):
    if course.state != "published":
        return _calculate_results_impl(course)

    cache_key = 'evap.staff.results.tools.calculate_results-{:d}'.format(course.id)
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

    for questionnaire, contributor, label, results, warning in calculate_results(course):
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


def send_publish_notifications(courses):
    publish_notifications = defaultdict(set)

    for course in courses:
        # for published courses all contributors and participants get a notification
        if course.can_publish_grades:
            for participant in course.participants.all():
                publish_notifications[participant].add(course)
            for contribution in course.contributions.all():
                if contribution.contributor:
                    publish_notifications[contribution.contributor].add(course)
        # if a course was not published notifications are only sent for contributors who can see comments
        elif len(course.textanswer_set) > 0:
            for textanswer in course.textanswer_set:
                if textanswer.contribution.contributor:
                    publish_notifications[textanswer.contribution.contributor].add(course)
            publish_notifications[course.responsible_contributor].add(course)

    for user, course_set in publish_notifications.items():
        EmailTemplate.send_publish_notifications_to_user(user, list(course_set))


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

    capped_deviation = min(deviation, 2.0) # values above that are very uncommon in practice
    val = int(255 - capped_deviation * 60) # tweaked to look good
    return (val, val, val)


def sort_formset(request, formset):
    if request.POST: # if not, there will be no cleaned_data and the models should already be sorted anyways
        formset.is_valid() # make sure all forms have cleaned_data
        formset.forms.sort(key=lambda f: f.cleaned_data.get("order", 9001) )


def course_types_in_semester(semester):
    return Course.objects.filter(semester=semester).values_list('type', flat=True).order_by().distinct()


def has_no_rating_answers(course, contributor, questionnaire):
    questions = questionnaire.rating_questions
    contribution = Contribution.objects.get(course=course, contributor=contributor)
    return RatingAnswerCounter.objects.filter(question__in=questions, contribution=contribution).count() == 0
