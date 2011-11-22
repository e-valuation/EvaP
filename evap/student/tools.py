def make_form_identifier(assignment, questionnaire, question):
    """Generates a form field identifier for voting forms using the given
    parameters."""
    
    return "question_%s_%s_%s" % (
        assignment.id,
        questionnaire.id,
        question.id)
