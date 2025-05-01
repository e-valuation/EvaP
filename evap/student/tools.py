from evap.evaluation.models import Contribution, Question, Questionnaire


def answer_field_id(
    contribution: Contribution, questionnaire: Questionnaire, question: Question, additional_textanswer: bool = False
) -> str:
    """Generates a form field identifier for voting forms using the given
    parameters."""

    identifier = f"question_{contribution.id}_{questionnaire.id}_{question.id}"
    if additional_textanswer:
        identifier += "_ta"
    return identifier


def parse_answer_field_id(formfield_id: str) -> tuple[int, int, int, bool]:
    """Parses the contribution-, questionnaire- and question-id from a formfield string,
    as well as if it is the field for the corresponding additional text answer"""

    parts = formfield_id.split("_")
    assert parts[0] == "question"

    if len(parts) == 5 and parts[4] == "ta":
        return *map(int, parts[1:4]), True  # type: ignore[return-value]
    assert len(parts) == 4
    return *map(int, parts[1:4]), False  # type: ignore[return-value]
