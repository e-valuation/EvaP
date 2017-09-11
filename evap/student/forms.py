from django import forms

from evap.student.tools import make_form_identifier
from evap.evaluation.tools import LIKERT_NAMES, GRADE_NAMES, POSITIVE_YES_NO_NAMES, NEGATIVE_YES_NO_NAMES

LIKERT_CHOICES = [(str(k), v) for k, v in LIKERT_NAMES.items()]
GRADE_CHOICES = [(str(k), v) for k, v in GRADE_NAMES.items()]
POSITIVE_YES_NO_CHOICES = [(str(k), v) for k, v in POSITIVE_YES_NO_NAMES.items()]
NEGATIVE_YES_NO_CHOICES = [(str(k), v) for k, v in NEGATIVE_YES_NO_NAMES.items()]


class QuestionsForm(forms.Form):
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

            identifier = make_form_identifier(contribution,
                                              questionnaire,
                                              question)

            identifier = question_id(self.contribution,
                                     self.questionnaire,
                                     question)

            self.fields[identifier] = field

    def caption(self):
        return self.questionnaire.public_name

    def teaser(self):
        return self.questionnaire.teaser
