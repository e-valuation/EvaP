from django import forms
from django.utils.translation import ugettext_lazy as _

from evap.student.tools import make_form_identifier
from evap.evaluation.models import UserProfile


GRADE_CHOICES = (
    (u"1", u"1"),
    (u"2", u"2"),
    (u"3", u"3"),
    (u"4", u"4"),
    (u"5", u"5"),
    (u"X", _(u"no answer"))
)


def coerce_grade(string_value):
    """Converts a grade string (first element of each GRADE_CHOICES pair) into
    an integer or None."""
    
    if string_value == u"X":
        return None
    return int(string_value)


class QuestionsForm(forms.Form):
    """Dynamic form class that adds one field per question. Pass the arguments
    `assignment` and `questionnaire` to the constructor.
    
    See http://jacobian.org/writing/dynamic-form-generation/"""
    
    def __init__(self, *args, **kwargs):
        self.assignment = kwargs.pop('assignment')
        self.questionnaire = kwargs.pop('questionnaire')
        
        super(QuestionsForm, self).__init__(*args, **kwargs)
        
        for question in self.questionnaire.question_set.all():
            # generic arguments for all kinds of fields
            field_args = dict(label=question.text)
            
            if question.is_text_question():
                field = forms.CharField(required=False, widget=forms.Textarea(),
                                        **field_args)
            elif question.is_grade_question():
                field = forms.TypedChoiceField(widget=forms.RadioSelect(),
                                               choices=GRADE_CHOICES,
                                               coerce=coerce_grade,
                                               **field_args)
            
            identifier = make_form_identifier(self.assignment,
                                              self.questionnaire,
                                              question)
            self.fields[identifier] = field

    def caption(self):
        if self.assignment.lecturer:
            try:
                full_name = self.assignment.lecturer.get_profile().full_name
            except UserProfile.DoesNotExist:
                full_name = self.assignment.lecturer.get_full_name() or self.assignment.lecturer.username
            return u"%s: %s" % (full_name, self.questionnaire.public_name)
        else:
            return self.questionnaire.public_name
    
    def teaser(self):
        return self.questionnaire.teaser
    
    def image(self):
        return self.assignment.lecturer.get_profile().picture if self.assignment.lecturer else None
