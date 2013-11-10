from django import forms
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import force_unicode
from django.utils.safestring import mark_safe


from evap.student.tools import make_form_identifier
from evap.evaluation.models import UserProfile
from evap.evaluation.tools import GRADE_NAMES


GRADE_CHOICES = [(unicode(k), v) for k, v in GRADE_NAMES.items()]
GRADE_CHOICES.append((u"X", _(u"no answer")))


def coerce_grade(string_value):
    """Converts a grade string (first element of each GRADE_CHOICES pair) into
    an integer or None."""
    
    if string_value == u"X":
        return None
    return int(string_value)


class RadioFieldTableRenderer(forms.widgets.RadioFieldRenderer):
    def render(self):
        """Outputs a <ul> for this set of radio fields."""
        return mark_safe(u'\n'.join([u'<div>%s</div>'
                % force_unicode(w) for w in self]))


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
                field = forms.TypedChoiceField(widget=forms.RadioSelect(renderer=RadioFieldTableRenderer),
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
                full_name = UserProfile.objects.get(user=self.assignment.lecturer).full_name
            except UserProfile.DoesNotExist:
                full_name = self.assignment.lecturer.get_full_name() or self.assignment.lecturer.username
            return u"%s: %s" % (full_name, self.questionnaire.public_name)
        else:
            return self.questionnaire.public_name
    
    def teaser(self):
        return self.questionnaire.teaser
    
    def image(self):
        return UserProfile.get_for_user(self.assignment.lecturer).picture if self.assignment.lecturer else None
