from django import forms
from django.utils.translation import ugettext_lazy as _

from evaluation.models import Semester, Course

class ImportForm(forms.Form):
    excel_file = forms.FileField()
    
class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester

class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        exclude = ("voters", "semester")