def answer_field_id(contribution, questionnaire, question, additional_textanswer=False):
    """Generates a form field identifier for voting forms using the given
    parameters."""

    identifier = f"question_{contribution.id}_{questionnaire.id}_{question.id}"
    if additional_textanswer:
        identifier += "_ta"
    return identifier
