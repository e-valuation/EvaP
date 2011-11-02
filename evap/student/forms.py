from django import forms
from django.utils.translation import ugettext_lazy as _

from evap.student.tools import make_form_identifier
from evap.evaluation.models import UserProfile
from evap.evaluation.tools import questionnaires_and_lecturers


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


class TextAnswerWidget(forms.MultiWidget):
    def __init__(self, *args, **kwargs):
        self.textfield = kwargs.pop('textfield')
        self.boolfield = kwargs.pop('boolfield')
        kwargs['widgets'] = [self.textfield.widget, self.boolfield.widget]
        super(TextAnswerWidget, self).__init__(*args, **kwargs)
    
    def format_output(self, rendered_widgets):
        # FIXME use actual html <label>
        return u"%s<br/>%s %s" % (rendered_widgets[0], rendered_widgets[1],
                                  self.boolfield.label)
    
    def decompress(self, value):
        if value:
            return value
        else:
            return "", False


class TextAnswerField(forms.MultiValueField):
    def __init__(self, *args, **kwargs):
        fields = (
            forms.CharField(required=False, widget=forms.Textarea()),
            forms.BooleanField(required=False, label=_(u"Publish text even if anonymity cannot be assured."))
        )
        super(TextAnswerField, self).__init__(fields, *args, **kwargs)
        self.widget = TextAnswerWidget(textfield=fields[0], boolfield=fields[1])
    
    def compress(self, data_list):
        return data_list


class QuestionsForm(forms.Form):
    """Dynamic form class that adds one field per question. Pass the arguments
    `questionnaire` and `lecturer` to the constructor.
    
    See http://jacobian.org/writing/dynamic-form-generation/"""
    
    def __init__(self, *args, **kwargs):
        self.questionnaire = kwargs.pop('questionnaire')
        self.lecturer = kwargs.pop('lecturer')
        
        super(QuestionsForm, self).__init__(*args, **kwargs)
        
        for question in self.questionnaire.question_set.all():
            # generic arguments for all kinds of fields
            field_args = dict(label=question.text)
            
            if question.is_text_question():
                field = TextAnswerField(required=False,
                                        **field_args)
            elif question.is_grade_question():
                field = forms.TypedChoiceField(widget=forms.RadioSelect(),
                                               choices=GRADE_CHOICES,
                                               coerce=coerce_grade,
                                               **field_args)
            
            identifier = make_form_identifier(self.questionnaire,
                                              question,
                                              self.lecturer)
            self.fields[identifier] = field

    def caption(self):
        if self.lecturer:
            try:
                full_name = self.lecturer.get_profile().full_name
            except UserProfile.DoesNotExist:
                full_name = self.lecturer.get_full_name() or self.lecturer.username
            
            return u"%s: %s" % (full_name, self.questionnaire.name)
            
        else:
            return self.questionnaire.name
    
    def image(self):
        return self.lecturer.get_profile().picture if self.lecturer else None
