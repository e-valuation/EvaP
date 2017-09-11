def question_id(contribution, questionnaire, question):
    """Generates a form field identifier for voting forms using the given
    parameters."""

    return "question_%s_%s_%s" % (
        contribution.id,
        questionnaire.id,
        question.id)
