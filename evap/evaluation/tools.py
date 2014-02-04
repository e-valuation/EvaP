from django.conf import settings
from django.core.cache import cache
from django.db.models import Min, Count
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext_lazy as _
from evap.evaluation.models import GradeAnswer, TextAnswer


from collections import namedtuple

GRADE_NAMES = {
    1: _(u"Strongly agree"),
    2: _(u"Agree"),
    3: _(u"Neither agree nor disagree"),
    4: _(u"Disagree"),
    5: _(u"Strongly disagree"),
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
ResultSection = namedtuple('ResultSection', ('questionnaire', 'contributor', 'results', 'average'))
GradeResult = namedtuple('GradeResult', ('question', 'count', 'average', 'variance', 'distribution', 'show'))
TextResult = namedtuple('TextResult', ('question', 'texts'))


def avg(iterable):
    """Simple arithmetic average function. Returns `None` if the length of
    `iterable` is 0 or no items except None exist."""
    items = [item for item in iterable if item is not None]
    if len(items) == 0:
        return None
    return float(sum(items)) / len(items)


def calculate_results(course):
    """Calculates the result data for a single course. Returns a list of
    `ResultSection` tuples. Each of those tuples contains the questionnaire, the
    contributor (or None), a list of single result elements and the average grade
    for that section (or None). The result elements are either `GradeResult` or
    `TextResult` instances."""
    
    # return cached results if available
    cache_key = 'evap.fsr.results.views.calculate_results-%d' % course.id
    prior_results = cache.get(cache_key)
    if prior_results:
        return prior_results
    
    # there will be one section per relevant questionnaire--contributor pair
    sections = []
    
    for questionnaire, contribution in questionnaires_and_contributions(course):
        # will contain one object per question
        results = []
        for question in questionnaire.question_set.all():
            if question.is_grade_question():
                # gather all numeric answers as a simple list
                answers = GradeAnswer.objects.filter(
                    contribution__course=course,
                    contribution__contributor=contribution.contributor,
                    question=question
                    ).values_list('answer', flat=True)
                
                # calculate average and distribution
                if answers:
                    # average
                    average = avg(answers)
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
                    variance = None
                    distribution = None
                
                # produce the result element
                results.append(GradeResult(
                    question=question,
                    count=len(answers),
                    average=average,
                    variance=variance,
                    distribution=distribution,
                    show=(len(answers) >= settings.MIN_ANSWERS)
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
        
        # compute average grade for this section, will return None if
        # no GradeResults exist in this section
        average_grade = avg([result.average for result
                                            in results
                                            if isinstance(result, GradeResult)])
        sections.append(ResultSection(questionnaire, contribution.contributor, results, average_grade))
    
    # store results into cache
    # XXX: What would be a good timeout here? Once public, data is not going to
    #      change anyway.
    cache.set(cache_key, sections, 24 * 60 * 60)
    
    return sections


def calculate_average_grade(course):
    """Determines the final grade for a course."""
    generic_grades = []
    personal_grades = []
    
    for questionnaire, contributor, results, average in calculate_results(course):
        if average:
            (personal_grades if contributor else generic_grades).append(average)
    
    if not generic_grades:
        # not final grade without any generic grade
        return None
    elif not personal_grades:
        # determine final grade by using the average of the generic grades
        return avg(generic_grades)
    else:
        # determine final grade by building the equally-weighted average of the
        # generic and person-specific averages
        return avg((avg(generic_grades), avg(personal_grades)))


def questionnaires_and_contributions(course):
    """Yields tuples of (questionnaire, contribution) for the given course."""
    result = []
    
    for contribution in course.contributions.annotate(Min("questionnaires__index")).order_by("questionnaires__is_for_contributors", "questionnaires__index__min"):
        for questionnaire in contribution.questionnaires.all():
            result.append((questionnaire, contribution))
    
    # sort questionnaires without contributors first
    result.sort(key=lambda t: t[1].contributor is not None)
    
    return result
