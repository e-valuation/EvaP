from django.db.models import Avg
from django.utils.datastructures import SortedDict
from evaluation.models import GradeAnswer, TextAnswer

from collections import namedtuple

# see calculate_results
GradeResult = namedtuple('GradeResult', ('question', 'average', 'count', 'distribution'))
TextResult = namedtuple('TextResult', ('question', 'texts'))


def avg(iterable):
    """Simple arithmetic average function. Returns `None` if the length of
    `iterable` is 0."""
    if len(iterable) == 0:
        return None
    return float(sum(iterable)) / len(iterable)


def calculate_results(course):
    """Calculates the result data for a single course. Returns a list of
    4-tuples. Each of those tuples contains the questionnaire, the lecturer
    (or None), a list of single result elements and the average grade for that
    section (or None). The result elements are either `GradeResult` or
    `TextResult` instances."""
    sections = []
    
    for questionnaire, lecturer in questionnaires_and_lecturers(course):
        results = [] # holds the single result elements
        for question in questionnaire.question_set.all():
            if question.is_grade_question():
                # gather all answers as a simple list
                answers = GradeAnswer.objects.filter(
                    course=course,
                    lecturer=lecturer,
                    question=question
                    ).values_list('answer', flat=True)
                
                # only add to the results if answers exist at all
                # XXX: what if only a few answers exist? (anonymity)
                if answers:
                    # calculate relative distribution of answers
                    distribution = SortedDict()
                    for i in range(1, 6):
                        distribution[i] = 0
                    for answer in answers:
                        distribution[answer] += 1
                    for k in distribution:
                        distribution[k] = int(float(distribution[k]) / len(answers) * 100)
                    
                    results.append(GradeResult(
                        question=question,
                        average=avg(answers),
                        count=len(answers),
                        distribution=distribution
                    ))
            elif question.is_text_question():
                # save all text answers for this question
                answers = TextAnswer.objects.filter(
                    course=course,
                    lecturer=lecturer,
                    question=question
                    )
                results.append(TextResult(
                    question=question,
                    texts=[answer.answer for answer in answers]
                ))
        if not results:
            continue
        
        # compute average grade for this section, will return None if no
        # GradeResults exist in this section
        average_grade = avg([result.average for result in results if isinstance(result, GradeResult)])
        sections.append((questionnaire, lecturer, results, average_grade))
    
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
    
    for questionnaire in course.general_questions.all():
        yield (questionnaire, None)
    for lecturer in course.primary_lecturers.all():
        for questionnaire in course.primary_lecturer_questions.all():
            yield (questionnaire, lecturer)
    for lecturer in course.secondary_lecturers.all():
        for questionnaire in course.secondary_lecturer_questions.all():
            yield (questionnaire, lecturer)
