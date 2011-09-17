from django.db.models import Avg
from django.utils.datastructures import SortedDict
from evaluation.models import GradeAnswer, TextAnswer

from collections import namedtuple, OrderedDict

GradeResult = namedtuple('GradeResult', ('question', 'average', 'count', 'distribution'))
TextResult = namedtuple('TextResult', ('question', 'texts'))

def calculate_results(course):
    sections = []
    
    for questionnaire, lecturer in questionnaires_and_lecturers(course):
        results = []
        for question in questionnaire.question_set.all():
            if question.is_grade_question():
                answers = GradeAnswer.objects.filter(
                    course=course,
                    lecturer=lecturer,
                    question=question
                    ).values_list('answer', flat=True)
                if answers:
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
                answers = TextAnswer.objects.filter(
                    course=course,
                    lecturer=lecturer,
                    question=question
                    )
                results.append(TextResult(
                    question=question,
                    texts=[answer.answer for answer in answers]
                ))
                
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
