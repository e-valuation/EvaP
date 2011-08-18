from django import forms
from django.utils.translation import ugettext_lazy as _

from evaluation.models import Semester, Course

class ImportForm(forms.Form):
    vote_start_date = forms.DateField(label = _(u"first date to vote"))
    vote_end_date = forms.DateField(label = _(u"last date to vote"))
    publish_date = forms.DateField(label = _(u"publishing date"))
    
    excel_file = forms.FileField(label = _(u"excel file"))
    
class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester

class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        exclude = ("voters", "semester")