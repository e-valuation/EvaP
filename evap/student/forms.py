from django import forms

from evap.evaluation.models import CHOICES, Contribution, Question, Questionnaire
from evap.student.tools import answer_field_id


class HeadingField(forms.Field):
    """Pseudo field used to store and display headings inside a QuestionnaireVotingForm.
    Does not handle any kind of input."""

    def __init__(self, label) -> None:
        super().__init__(label=label, required=False)

    @classmethod
    def from_question(cls, question: Question) -> "HeadingField":
        return cls(label=question.text)


class TextAnswerField(forms.CharField):
    def __init__(self, *args, related_answer_field_id: str | None = None, **kwargs) -> None:
        self.related_answer_field_id = related_answer_field_id
        kwargs["required"] = False
        kwargs["widget"] = forms.Textarea(attrs={"related_answer_field_id": self.related_answer_field_id})
        super().__init__(*args, **kwargs)

    @classmethod
    def from_question(cls, question: Question) -> "TextAnswerField":
        return cls(label=question.text)


class RatingAnswerField(forms.TypedChoiceField):
    def __init__(self, widget_choices, *args, allows_textanswer: bool = False, **kwargs) -> None:
        self.allows_textanswer = allows_textanswer
        kwargs["coerce"] = int
        kwargs["widget"] = forms.RadioSelect(
            attrs={
                "allows_textanswer": self.allows_textanswer,
                "choices": widget_choices,
            }
        )
        super().__init__(*args, **kwargs)

    @classmethod
    def from_question(cls, question: Question) -> "RatingAnswerField":
        return cls(
            widget_choices=CHOICES[question.type],
            choices=zip(CHOICES[question.type].values, CHOICES[question.type].names, strict=True),
            label=question.text,
            allows_textanswer=question.allows_additional_textanswers,
        )


def question_fields(
    question: Question, identifier: str, additional_textanswer_identifier: str
) -> dict[str, forms.Field]:
    """Creates the form fields for a question, including the field for an additional text answer if allowed.
    The additional text answer field must directly follow the rating field, as the template relies on this order."""

    field: TextAnswerField | RatingAnswerField | HeadingField
    if question.is_text_question:
        field = TextAnswerField.from_question(question)
    elif question.is_rating_question:
        field = RatingAnswerField.from_question(question)
    else:
        assert question.is_heading_question
        field = HeadingField.from_question(question)

    fields: dict[str, forms.Field] = {identifier: field}
    if question.is_rating_question and question.allows_additional_textanswers:
        fields[additional_textanswer_identifier] = TextAnswerField(
            label=question.text, related_answer_field_id=identifier
        )
    return fields


class QuestionnaireVotingForm(forms.Form):
    """Dynamic form class that adds required fields per question.

    See http://jacobian.org/writing/dynamic-form-generation/"""

    def __init__(self, *args, contribution: Contribution, questionnaire: Questionnaire, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.questionnaire = questionnaire

        for assignment in self.questionnaire.question_assignments.all():
            question = assignment.question
            self.fields.update(
                question_fields(
                    question,
                    answer_field_id(contribution, questionnaire, question),
                    answer_field_id(contribution, questionnaire, question, additional_textanswer=True),
                )
            )
