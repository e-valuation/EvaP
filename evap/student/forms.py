from django import forms

from evap.student.tools import question_id
from evap.evaluation.models import CHOICES


class HeadingField(forms.Field):
    """ Pseudo field used to store and display headings inside a QuestionnaireVotingForm.
    Does not handle any kind of input."""

    def __init__(self, label):
        super().__init__(label=label, required=False)


class QuestionnaireVotingForm(forms.Form):
    """Dynamic form class that adds one field per question.

    See http://jacobian.org/writing/dynamic-form-generation/"""

    def __init__(self, *args, contribution, questionnaire, **kwargs):
        super().__init__(*args, **kwargs)
        self.questionnaire = questionnaire

        for question in self.questionnaire.questions.all():
            # generic arguments for all kinds of fields
            field_args = dict(label=question.text)

            if question.is_text_question:
                field = forms.CharField(required=False, widget=forms.Textarea(),
                                        **field_args)
            elif question.is_rating_question:
                choices = CHOICES[question.type]
                field = forms.TypedChoiceField(widget=forms.RadioSelect(attrs={'choices': choices}),
                                               choices=zip(choices.values, choices.names),
                                               coerce=int,
                                               **field_args)
            elif question.is_heading_question:
                field = HeadingField(label=question.text)

            identifier = question_id(contribution,
                                     questionnaire,
                                     question)

            self.fields[identifier] = field
