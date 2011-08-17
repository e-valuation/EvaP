from django import forms
from django.utils.translation import ugettext_lazy as _

from evaluation.models import Semester

class ImportForm(forms.Form):
    excel_file = forms.FileField()
    
class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester