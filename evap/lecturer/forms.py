from django import forms
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import Course, UserProfile, Questionnaire
from evap.evaluation.forms import BootstrapMixin, QuestionnaireMultipleChoiceField


class CourseForm(forms.ModelForm, BootstrapMixin):
    general_questions = QuestionnaireMultipleChoiceField(Questionnaire.objects.filter(is_for_persons=False, obsolete=False), label=_(u"General questions"))
    
    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'vote_start_date', 'vote_end_date', 'kind', 'study', 'general_questions')
    
    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)

        self.fields['vote_start_date'].localize = False
        self.fields['vote_end_date'].localize = False        
        self.fields['kind'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('kind', flat=True).order_by().distinct()])        
        self.fields['study'].widget.attrs['readonly'] = True
        
        if self.instance.general_assignment:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_assignment.questionnaires.all()]
        
    def clean_study(self):
        return self.instance.study

    def save(self, *args, **kw):
        user = kw.pop("user")
        super(CourseForm, self).save(*args, **kw)
        self.instance.general_assignment.questionnaires = self.cleaned_data.get('general_questions')
        self.instance.last_modified_user = user
        self.instance.save()
    
    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        exclude.remove('semester') # allow checking against the missing attribute
        
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError, e:
            self._update_errors(e.message_dict)


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
        self.instance = UserProfile.get_for_user(self.instance.user)
        
        super(UserForm, self).save(*args, **kw)
