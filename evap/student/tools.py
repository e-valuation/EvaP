def make_form_identifier(question_group, question, user):
    """Generates a form field identifier for voting forms using the given
    parameters."""
    
    return "question_%s_%s_%s" % (
        question_group.id,
        user.id if user else '',
        question.id)

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
