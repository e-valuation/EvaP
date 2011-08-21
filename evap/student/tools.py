def make_form_identifier(question_group, question, user):
    """Generates a form field identifier for voting forms using the given
    parameters."""
    
    return "question_%s_%s_%s" % (
        question_group.id,
        user.id if user else '',
        question.id)
