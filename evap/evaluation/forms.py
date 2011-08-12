from django import forms
from django.utils.translation import ugettext_lazy as _

GRADE_CHOICES = (
    (u"1", u"1"),
    (u"2", u"2"),
    (u"3", u"3"),
    (u"4", u"4"),
    (u"5", u"5"),
    (u"X", _(u"no answer"))
)

def coerce_grade(s):
    if s == u"X":
        return None
    return int(s)


class QuestionsForms(forms.Form):
    """Dynamic form class that adds one field per question. Pass an iterable
    of questionnaires as `questionnaires` argument to the initializer.
    
    See http://jacobian.org/writing/dynamic-form-generation/"""
    
    def __init__(self, *args, **kwargs):
        questionnaires = kwargs.pop('questionnaires')
        super(QuestionsForms, self).__init__(*args, **kwargs)
        
        for questionnaire in questionnaires:
            for question in questionnaire.questions():
                field_args = dict(label=question.text)
                
                if question.is_text_question():
                    field = forms.CharField(widget=forms.Textarea(),
                                            required=False,
                                            **field_args)
                elif question.is_grade_question():
                    field = forms.TypedChoiceField(widget=forms.RadioSelect(),
                                                   choices=GRADE_CHOICES,
                                                   coerce=coerce_grade,
                                                   **field_args)
                
                self.fields['question_%d_%d' % (questionnaire.id, question.id)] = field
