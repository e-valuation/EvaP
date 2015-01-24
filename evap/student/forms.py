from django import forms
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe


from evap.student.tools import make_form_identifier
from evap.evaluation.tools import LIKERT_NAMES, GRADE_NAMES


LIKERT_CHOICES = [(str(k), v) for k, v in LIKERT_NAMES.items()]
GRADE_CHOICES = [(str(k), v) for k, v in GRADE_NAMES.items()]

class QuestionsForm(forms.Form):
    """Dynamic form class that adds one field per question. Pass the arguments
    `contribution` and `questionnaire` to the constructor.

    See http://jacobian.org/writing/dynamic-form-generation/"""

    def __init__(self, *args, **kwargs):
        self.contribution = kwargs.pop('contribution')
        self.questionnaire = kwargs.pop('questionnaire')

        super(QuestionsForm, self).__init__(*args, **kwargs)

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

            identifier = make_form_identifier(self.contribution,
                                              self.questionnaire,
                                              question)
            self.fields[identifier] = field

    def caption(self):
        return self.questionnaire.public_name

    def teaser(self):
        return self.questionnaire.teaser
