from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from evap.evaluation.forms import BootstrapMixin

from evap.grades.models import GradeDocument


class StrippedCharField(forms.CharField):
    """
        CharField that saves trimmed strings
    """

    def to_python(self, value):
        super(StrippedCharField, self).to_python(value)
        if value is None:
            return None
        return value.strip()


class GradeDocumentForm(forms.ModelForm, BootstrapMixin):
    description = StrippedCharField(label=_("Description"), max_length=255)
    # see CourseForm (staff/forms.py) for details, why the following two fields are needed
    last_modified_time_2 = forms.DateTimeField(label=_("Last modified"), required=False, localize=True)
    last_modified_user_2 = forms.CharField(label=_("Last modified by"), required=False)

    class Meta:
        model = GradeDocument
        fields = ('description', 'file', 'last_modified_time_2', 'last_modified_user_2')
        exclude = ('course',)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        final_grades = kwargs.pop('final_grades')
        course = kwargs.pop('course')
        super().__init__(*args, **kwargs)

        if final_grades:
            self.fields['description'].initial = settings.DEFAULT_FINAL_GRADES_DESCRIPTION
        else:
            self.fields['description'].initial = settings.DEFAULT_MIDTERM_GRADES_DESCRIPTION

        if self.instance.last_modified_user:
            self.fields['last_modified_time_2'].widget.attrs['readonly'] = True
            self.fields['last_modified_user_2'].widget.attrs['readonly'] = True
            self.fields['last_modified_time_2'].initial = self.instance.last_modified_time
            self.fields['last_modified_user_2'].initial = self.instance.last_modified_user.full_name
        else:
            self.fields['last_modified_time_2'].widget = forms.HiddenInput()
            self.fields['last_modified_user_2'].widget = forms.HiddenInput()
        
        self.instance.course = course
        if final_grades:
            self.instance.type = GradeDocument.FINAL_GRADES
        self.instance.last_modified_user = user

    def clean_description(self):
        description = self.cleaned_data.get('description')
        if GradeDocument.objects.filter(course=self.instance.course, description=description).exclude(id=self.instance.id).exists():
            raise ValidationError(_("This description for a grade document was already used for this course."))
        return description
