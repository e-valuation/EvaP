from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg
from django.utils.datastructures import SortedDict
from evap.evaluation.models import GradeAnswer, TextAnswer

from collections import namedtuple

# see calculate_results
ResultSection = namedtuple('CourseResult', ('questionnaire', 'lecturer', 'results', 'average'))
GradeResult = namedtuple('GradeResult', ('question', 'average', 'count', 'distribution', 'show'))
TextResult = namedtuple('TextResult', ('question', 'texts'))


def avg(iterable):
    """Simple arithmetic average function. Returns `None` if the length of
    `iterable` is 0."""
    if len(iterable) == 0:
        return None
    return float(sum(iterable)) / len(iterable)


def calculate_results(course):
    """Calculates the result data for a single course. Returns a list of
    `ResultSection` tuples. Each of those tuples contains the questionnaire, the
    lecturer (or None), a list of single result elements and the average grade
    for that section (or None). The result elements are either `GradeResult` or
    `TextResult` instances."""
    
    # return cached results if available
    cache_key = 'evap.fsr.results.views.calculate_results-%d' % course.id
    prior_results = cache.get(cache_key)
    if prior_results:
        return prior_results
    
    # there will be one section per relevant questionnaire--lecturer pair
    sections = []
    
    for questionnaire, lecturer in questionnaires_and_lecturers(course):
        # will contain one object per question
        results = []
        for question in questionnaire.question_set.all():
            if question.is_grade_question():
                # gather all numeric answers as a simple list
                answers = GradeAnswer.objects.filter(
                    assignment__course=course,
                    assignment__lecturer=lecturer,
                    question=question
                    ).values_list('answer', flat=True)
                
                # calculate average and distribution
                if answers:
                    # average
                    average = avg(answers)
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
                        distribution[k] = int(float(distribution[k]) / len(answers) * 100)
                else:
                    average = None
                    distribution = None
                
                # produce the result element
                results.append(GradeResult(
                    question=question,
                    average=avg(answers),
                    count=len(answers),
                    distribution=distribution,
                    show=(len(answers) >= settings.MIN_ANSWERS)
                ))
            
            elif question.is_text_question():
                # gather text answers for this question
                answers = TextAnswer.objects.filter(
                    course=course,
                    lecturer=lecturer,
                    question=question
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
                                            if isinstance(result, GradeResult) and result.show])
        sections.append(ResultSection(questionnaire, lecturer, results, average_grade))
    
    # store results into cache
    # XXX: What would be a good timeout here? Once public, data is not going to
    #      change anyway.
    cache.set(cache_key, sections, 24*60*60)
    
    return sections


def calculate_average_grade(course):
    """Determines the final grade for a course."""
    generic_grades = []
    personal_grades = []
    
    for questionnaire, lecturer, results, average in calculate_results(course):
        if average:
            (personal_grades if lecturer else generic_grades).append(average)
    
    if not generic_grades:
        # not final grade without any generic grade
        return None
    elif not personal_grades:
        # determine final grade by using the average of the generic grades
        return avg(generic_grades)
    else:
        # determine final grade by building the equally-weighted average of the
        # generic and person-specific averages
        return (avg(generic_grades) + avg(personal_grades)) / 2


def questionnaires_and_lecturers(course):
    """Yields tuples of (questionnaire, lecturer) for the given course. The
    lecturer is None for general questionnaires."""
    
    for assignment in course.assignments.all():
        for questionnaire in assignment.questionnaires.all():
            yield (questionnaire, assignment.lecturer)
