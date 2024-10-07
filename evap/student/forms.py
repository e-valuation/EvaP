from django import forms

from evap.evaluation.models import CHOICES, Question
from evap.student.tools import answer_field_id


class HeadingField(forms.Field):
    """Pseudo field used to store and display headings inside a QuestionnaireVotingForm.
    Does not handle any kind of input."""

    def __init__(self, label):
        super().__init__(label=label, required=False)

    @classmethod
    def from_question(cls, question: Question):
        return cls(label=question.text)


class TextAnswerField(forms.CharField):
    def __init__(self, *args, related_answer_field_id=None, **kwargs):
        self.related_answer_field_id = related_answer_field_id
        kwargs["required"] = False
        kwargs["widget"] = forms.Textarea(attrs={"related_answer_field_id": self.related_answer_field_id})
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["required"]
        del kwargs["widget"]
        if self.related_answer_field_id is not None:
            kwargs["related_answer_field_id"] = self.related_answer_field_id
        return name, path, args, kwargs

    @classmethod
    def from_question(cls, question: Question):
        return cls(label=question.text)


class RatingAnswerField(forms.TypedChoiceField):
    def __init__(self, widget_choices, *args, allows_textanswer=False, **kwargs):
        self.allows_textanswer = allows_textanswer
        kwargs["coerce"] = int
        kwargs["widget"] = forms.RadioSelect(
            attrs={
                "allows_textanswer": self.allows_textanswer,
                "choices": widget_choices,
            }
        )
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["coerce"]
        del kwargs["widget"]
        if self.allows_textanswer:
            kwargs["allows_textanswer"] = self.allows_textanswer
        return name, path, args, kwargs

    @classmethod
    def from_question(cls, question: Question):
        return cls(
            widget_choices=CHOICES[question.type],
            choices=zip(CHOICES[question.type].values, CHOICES[question.type].names, strict=True),
            label=question.text,
            allows_textanswer=question.allows_additional_textanswers,
        )


class QuestionnaireVotingForm(forms.Form):
    """Dynamic form class that adds required fields per question.

    See http://jacobian.org/writing/dynamic-form-generation/"""

    def __init__(self, *args, contribution, questionnaire, **kwargs):
        super().__init__(*args, **kwargs)
        self.questionnaire = questionnaire

        for question in self.questionnaire.questions.all():
            if question.is_text_question:
                field = TextAnswerField.from_question(question)
            elif question.is_rating_question:
                field = RatingAnswerField.from_question(question)
            else:
                assert question.is_heading_question
                field = HeadingField.from_question(question)

            identifier = answer_field_id(contribution, questionnaire, question)
            self.fields[identifier] = field

            if question.is_rating_question and question.allows_additional_textanswers:
                textanswer_field = TextAnswerField(label=question.text, related_answer_field_id=identifier)
                textanswer_identifier = answer_field_id(
                    contribution, questionnaire, question, additional_textanswer=True
                )
                self.fields[textanswer_identifier] = textanswer_field
