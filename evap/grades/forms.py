from django import forms
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from evap.evaluation.forms import BootstrapMixin

from evap.grades.models import GradeDocument


class GradeDocumentForm(forms.ModelForm, BootstrapMixin):
    # see CourseForm (staff/forms.py) for details, why the following two fields are needed
    last_modified_time_2 = forms.DateTimeField(label=_("Last modified"), required=False, localize=True, disabled=True)
    last_modified_user_2 = forms.CharField(label=_("Last modified by"), required=False, disabled=True)

    class Meta:
        model = GradeDocument
        fields = ('description_de', 'description_en', 'file', 'last_modified_time_2', 'last_modified_user_2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.last_modified_user:
            self.fields['last_modified_time_2'].initial = self.instance.last_modified_time
            self.fields['last_modified_user_2'].initial = self.instance.last_modified_user.full_name
        else:
            self.fields['last_modified_time_2'].widget = forms.HiddenInput()
            self.fields['last_modified_user_2'].widget = forms.HiddenInput()

    def clean_description_de(self):
        description_de = self.cleaned_data.get('description_de')
        if GradeDocument.objects.filter(course=self.instance.course, description_de__iexact=description_de).exclude(id=self.instance.id).exists():
            raise ValidationError(_("This description for a grade document was already used for this course."))
        return description_de

    def clean_description_en(self):
        description_en = self.cleaned_data.get('description_en')
        if GradeDocument.objects.filter(course=self.instance.course, description_en__iexact=description_en).exclude(id=self.instance.id).exists():
            raise ValidationError(_("This description for a grade document was already used for this course."))
        return description_en

    def save(self, modifying_user, *args, **kwargs):
        self.instance.last_modified_user = modifying_user
        super().save(*args, **kwargs)
