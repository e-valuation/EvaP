from django import forms
from django.utils.translation import ugettext_lazy as _
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
    description = StrippedCharField(max_length=255)
    last_modified_time_2 = forms.DateTimeField(label=_("Last modified"), required=False, localize=True)
    last_modified_user_2 = forms.CharField(label=_("Last modified by"), required=False)

    class Meta:
        model = GradeDocument
        fields = ('description', 'file', 'last_modified_time_2', 'last_modified_user_2')
        exclude = ('course',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['description'].help_text = _('e.g. "Preliminary test" or "Final grades"')

        self.fields['last_modified_time_2'].initial = self.instance.last_modified_time
        self.fields['last_modified_time_2'].widget.attrs['readonly'] = "True"
        if self.instance.last_modified_user:
            self.fields['last_modified_user_2'].initial = self.instance.last_modified_user.full_name
        self.fields['last_modified_user_2'].widget.attrs['readonly'] = "True"
