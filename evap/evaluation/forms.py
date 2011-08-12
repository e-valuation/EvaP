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
    of questions as `questions` argument to the initializer.
    
    See http://jacobian.org/writing/dynamic-form-generation/"""
    
    def __init__(self, *args, **kwargs):
        questions = kwargs.pop('questions')
        super(QuestionsForms, self).__init__(*args, **kwargs)
        
        for question in questions:
            field_args = dict(label=question.text)
            
            if question.kind == u"T":
                field = forms.CharField(widget=forms.Textarea(),
                                        required=False,
                                        **field_args)
            elif question.kind == u"G":
                field = forms.TypedChoiceField(widget=forms.RadioSelect(),
                                               choices=GRADE_CHOICES,
                                               coerce=coerce_grade,
                                               **field_args)
            else:
                raise Exception("Unknown kind of question: %s" % question.kind)
            
            self.fields['question_%d' % question.id] = field

