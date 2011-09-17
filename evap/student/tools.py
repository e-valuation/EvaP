def make_form_identifier(questionnaire, question, user):
    """Generates a form field identifier for voting forms using the given
    parameters."""
    
    return "question_%s_%s_%s" % (
        questionnaire.id,
        user.id if user else '',
        question.id)
