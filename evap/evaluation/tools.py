from django.conf import settings
from django.core.cache import cache
from django.db.models import Min, Count
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext_lazy as _
from evap.evaluation.models import LikertAnswer, TextAnswer, GradeAnswer


from collections import namedtuple

LIKERT_NAMES = {
    1: _(u"Strongly agree"),
    2: _(u"Agree"),
    3: _(u"Neither agree nor disagree"),
    4: _(u"Disagree"),
    5: _(u"Strongly disagree"),
    6: _(u"no answer"),
}

GRADE_NAMES = {
    1: _(u"1"),
    2: _(u"2"),
    3: _(u"3"),
    4: _(u"4"),
    5: _(u"5"),
    6: _(u"no answer"),
}

STATES_ORDERED = SortedDict((
    ('new', _('new')),
    ('prepared', _('prepared')),
    ('lecturerApproved', _('lecturer approved')),
    ('approved', _('approved')),
    ('inEvaluation', _('in evaluation')),
    ('evaluated', _('evaluated')),
    ('reviewed', _('reviewed')),
    ('published', _('published'))
))


# see calculate_results
ResultSection = namedtuple('ResultSection', ('questionnaire', 'contributor', 'results', 'average_likert', 'median_likert', 'average_grade', 'median_grade', 'average_total', 'median_total'))
LikertResult = namedtuple('LikertResult', ('question', 'count', 'average', 'median', 'variance', 'distribution', 'show'))
TextResult = namedtuple('TextResult', ('question', 'texts'))
GradeResult = namedtuple('GradeResult', ('question', 'count', 'average', 'median', 'variance', 'distribution', 'show'))


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
    if not length % 2:
        return (sorted_items[length / 2] + sorted_items[length / 2 - 1]) / 2.0
    return sorted_items[length / 2]

def mix(a, b, alpha):
    if a == None and b == None:
        return None
    if a == None:
        return b
    if b == None:
        return a

    return alpha * a + (1 - alpha) * b


def calculate_results(course, staff_member=False):
    """Calculates the result data for a single course. Returns a list of
    `ResultSection` tuples. Each of those tuples contains the questionnaire, the
    contributor (or None), a list of single result elements, the average and
    median grades for that section (or None). The result elements are either
    `LikertResult`, `TextResult` or `GradeResult` instances."""

    # return cached results if available
    cache_key = str.format('evap.fsr.results.views.calculate_results-{:d}-{:d}', course.id, staff_member)
    prior_results = cache.get(cache_key)
    if prior_results:
        return prior_results

    # check if grades for the course will be published
    show = staff_member or course.can_publish_grades()

    # there will be one section per relevant questionnaire--contributor pair
    sections = []

    for questionnaire, contribution in questionnaires_and_contributions(course):
        # will contain one object per question
        results = []
        for question in questionnaire.question_set.all():
            if question.is_likert_question():
                # gather all numeric answers as a simple list
                answers = LikertAnswer.objects.filter(
                    contribution__course=course,
                    contribution__contributor=contribution.contributor,
                    question=question
                    ).values_list('answer', flat=True)

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
                    distribution = SortedDict()
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

                # produce the result element
                results.append(LikertResult(
                    question=question,
                    count=len(answers),
                    average=average,
                    median=median,
                    variance=variance,
                    distribution=distribution,
                    show=show
                ))
            elif question.is_grade_question():
                # gather all numeric answers as a simple list
                answers = GradeAnswer.objects.filter(
                    contribution__course=course,
                    contribution__contributor=contribution.contributor,
                    question=question
                    ).values_list('answer', flat=True)

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
                    distribution = SortedDict()
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

                # produce the result element
                results.append(GradeResult(
                    question=question,
                    count=len(answers),
                    average=average,
                    median=median,
                    variance=variance,
                    distribution=distribution,
                    show=show
                ))
            elif question.is_text_question():
                # gather text answers for this question
                answers = TextAnswer.objects.filter(
                    contribution__course=course,
                    contribution__contributor=contribution.contributor,
                    question=question,
                    hidden=False
                    )
                # only add to the results if answers exist at all
                if answers:
                    results.append(TextResult(
                        question=question,
                        texts=[answer.answer for answer in answers]
                    ))

        # skip section if there were no questions with results
        if not results:
            continue

        # compute average and median grades for all LikertResults in this
        # section, will return None if no LikertResults exist in this section
        average_likert = avg([result.average for result
                                            in results
                                            if isinstance(result, LikertResult)])
        median_likert = med([result.median for result
                                            in results
                                            if isinstance(result, LikertResult)])

        # compute average and median grades for all GradeResults in this
        # section, will return None if no GradeResults exist in this section
        average_grade = avg([result.average for result
                                            in results
                                            if isinstance(result, GradeResult)])
        median_grade = med([result.median for result
                                            in results
                                            if isinstance(result, GradeResult)])

        average_total = mix(average_grade, average_likert, settings.GRADE_PERCENTAGE)
        median_total = mix(median_grade, median_likert, settings.GRADE_PERCENTAGE)
        
        sections.append(ResultSection(questionnaire, contribution.contributor, results,
            average_likert, median_likert,
            average_grade, median_grade,
            average_total, median_total))

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

    for questionnaire, contributor, results, average_likert, median_likert, average_grade, median_grade, average_total, median_total in calculate_results(course):
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


def questionnaires_and_contributions_by_contributor(course):
    """Yields a dictionary of contributors with a list of tuples (questionnaire, contribution) for the given course."""
    result = {}

    for contribution in course.contributions.annotate(Min("questionnaires__index")).order_by("questionnaires__is_for_contributors", "questionnaires__index__min"):
        if not contribution.contributor in result:
            result[contribution.contributor] = []
        for questionnaire in contribution.questionnaires.all():
            result[contribution.contributor].append((questionnaire, contribution))

    return result


def questionnaires_and_contributions(course):
    """Yields tuples of (questionnaire, contribution) for the given course."""
    result = []

    for contribution in course.contributions.annotate(Min("questionnaires__index")).order_by("questionnaires__is_for_contributors", "questionnaires__index__min"):
        for questionnaire in contribution.questionnaires.all():
            result.append((questionnaire, contribution))

    # sort questionnaires without contributors first
    result.sort(key=lambda t: t[1].contributor is not None)

    return result
