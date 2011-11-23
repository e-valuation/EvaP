from django import forms
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import *
from evap.fsr.fields import *


class CourseForm(forms.ModelForm):    
    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'kind')
    
    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)


class UserForm(forms.ModelForm):
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.CharField(required=False)
    
    proxies = UserModelMultipleChoiceField(queryset=User.objects.all())
    
    class Meta:
        model = UserProfile
        fields = ('title', 'first_name', 'last_name', 'email', 'picture', 'proxies')
    
    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        
        # fix generated form
        self.fields['proxies'].required = False
        
        # load user fields
        self.fields['first_name'].initial = self.instance.user.first_name
        self.fields['last_name'].initial = self.instance.user.last_name
        self.fields['email'].initial = self.instance.user.email

    def save(self, *args, **kw):
        # first save the user, so that the profile gets created for sure
        self.instance.user.first_name = self.cleaned_data.get('first_name')
        self.instance.user.last_name = self.cleaned_data.get('last_name')
        self.instance.user.email = self.cleaned_data.get('email')
        self.instance.user.save()
        self.instance = self.instance.user.get_profile()
        
        super(UserForm, self).save(*args, **kw)
