from django import forms
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import Course, UserProfile
from evap.evaluation.forms import BootstrapMixin
from evap.fsr.fields import UserModelMultipleChoiceField


class CourseForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'vote_start_date', 'vote_end_date', 'kind', 'study')
    
    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)
        
        for field in ['kind', 'study']:
            self.fields[field].widget.attrs['readonly'] = True
    
    def clean_kind(self):
        return self.instance.kind
    
    def clean_study(self):
        return self.instance.study


class UserForm(forms.ModelForm, BootstrapMixin):
    # steal form field definitions for the User model
    locals().update(forms.fields_for_model(User, fields=('first_name', 'last_name', 'email')))
    
    class Meta:
        model = UserProfile
        fields = ('title', 'first_name', 'last_name', 'email', 'picture', 'proxies')
    
    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        
        # fix generated form
        self.fields['proxies'].required = False
        self.fields['proxies'].queryset = User.objects.order_by("username")
        
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
