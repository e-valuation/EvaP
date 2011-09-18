from django.db.models import Avg
from django.utils.datastructures import SortedDict
from evaluation.models import GradeAnswer, TextAnswer

from collections import namedtuple, OrderedDict

GradeResult = namedtuple('GradeResult', ('question', 'average', 'count', 'distribution'))
TextResult = namedtuple('TextResult', ('question', 'texts'))

def calculate_results(course):
    """Calculates the result data for a single course. Returns a list of
    3-tuples. Each of those tuples contains the questionnaire, the lecturer
    (or None), and a list of single result elements. The result elements are
    either `GradeResult` or `TextResult` instances."""
    sections = []
    
    for questionnaire, lecturer in questionnaires_and_lecturers(course):
        results = []
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
                        average=float(sum(answers)/len(answers)),
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
        
        # only add to results if answers exist
        if results:
            sections.append((questionnaire, lecturer, results))
    
    return sections


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
