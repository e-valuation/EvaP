from django import forms
from django.utils.translation import ugettext_lazy as _

from student.tools import make_form_identifier, questiongroups_and_lecturers

GRADE_CHOICES = (
    (u"1", u"1"),
    (u"2", u"2"),
    (u"3", u"3"),
    (u"4", u"4"),
    (u"5", u"5"),
    (u"X", _(u"no answer"))
)

def coerce_grade(s):
    """Converts a grade string (first element of each GRADE_CHOICES pair) into
    an integer or None."""
    
    if s == u"X":
        return None
    return int(s)

class QuestionsForms(forms.Form):
    """Dynamic form class that adds one field per question. Pass the arguments
    `question_group` and `lecturer` to the constructor.
    
    See http://jacobian.org/writing/dynamic-form-generation/"""
    
    def __init__(self, *args, **kwargs):
        self.question_group = kwargs.pop('question_group')
        self.lecturer = kwargs.pop('lecturer')
        
        super(QuestionsForms, self).__init__(*args, **kwargs)
        
        for question in self.question_group.question_set.all():
            # generic arguments for all kinds of fields
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
            
            identifier = make_form_identifier(self.question_group,
                                              question,
                                              self.lecturer)
            self.fields[identifier] = field

    def caption(self):
        if self.lecturer:
            # FIXME needs better lecturer label
            return u"%s: %s" % (
                self.lecturer.username,
                self.question_group.name
            )
        else:
            return self.question_group.name
