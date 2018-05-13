from django import forms

from evap.student.tools import question_id
from evap.evaluation.tools import LIKERT_NAMES, GRADE_NAMES, POSITIVE_YES_NO_NAMES, NEGATIVE_YES_NO_NAMES

LIKERT_CHOICES = [(str(k), v) for k, v in LIKERT_NAMES.items()]
GRADE_CHOICES = [(str(k), v) for k, v in GRADE_NAMES.items()]
POSITIVE_YES_NO_CHOICES = [(str(k), v) for k, v in POSITIVE_YES_NO_NAMES.items()]
NEGATIVE_YES_NO_CHOICES = [(str(k), v) for k, v in NEGATIVE_YES_NO_NAMES.items()]


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

        for question in self.questionnaire.question_set.all():
            # generic arguments for all kinds of fields
            field_args = dict(label=question.text)

            if question.is_text_question:
                field = forms.CharField(required=False, widget=forms.Textarea(),
                                        **field_args)
            elif question.is_likert_question:
                field = forms.TypedChoiceField(widget=forms.RadioSelect(),
                                               choices=LIKERT_CHOICES,
                                               coerce=int,
                                               **field_args)
            elif question.is_grade_question:
                field = forms.TypedChoiceField(widget=forms.RadioSelect(),
                                               choices=GRADE_CHOICES,
                                               coerce=int,
                                               **field_args)
            elif question.is_positive_yes_no_question:
                field = forms.TypedChoiceField(widget=forms.RadioSelect(),
                                               choices=POSITIVE_YES_NO_CHOICES,
                                               coerce=int,
                                               **field_args)
            elif question.is_negative_yes_no_question:
                field = forms.TypedChoiceField(widget=forms.RadioSelect(),
                                               choices=NEGATIVE_YES_NO_CHOICES,
                                               coerce=int,
                                               **field_args)
            elif question.is_heading_question:
                field = HeadingField(label=question.text)

            identifier = question_id(contribution,
                                     questionnaire,
                                     question)

            self.fields[identifier] = field
