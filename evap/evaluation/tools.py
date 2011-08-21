from django.db.models import Avg
from evaluation.models import GradeAnswer


def calculate_results(course):
    results = []
    
    for question_group, lecturer in questiongroups_and_lecturers(course):
        averages = []
        for question in question_group.question_set.filter(kind="G"):
            average = GradeAnswer.objects.filter(
                course=course,
                lecturer=lecturer,
                question=question
                ).aggregate(Avg('answer'))['answer__avg']
            if average:
                averages.append((question, average))
        if averages:
            results.append((question_group, lecturer, averages))
    
    return results

def questiongroups_and_lecturers(course):
    """Yields tuples of (question_group, lecturer) for the given course. The
    lecturer is None for general question groups."""
    
    for question_group in course.general_questions.all():
        yield (question_group, None)
    for lecturer in course.primary_lecturers.all():
        for question_group in course.primary_lecturer_questions.all():
            yield (question_group, lecturer)
    for lecturer in course.secondary_lecturers.all():
        for question_group in course.secondary_lecturer_questions.all():
            yield (question_group, lecturer)
