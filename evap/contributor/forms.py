from django import forms
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import Course, UserProfile, Questionnaire
from evap.evaluation.forms import BootstrapMixin, QuestionnaireMultipleChoiceField


class CourseForm(forms.ModelForm, BootstrapMixin):
    general_questions = QuestionnaireMultipleChoiceField(Questionnaire.objects.filter(is_for_contributors=False, obsolete=False), label=_(u"General questions"))

    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'vote_start_date', 'vote_end_date', 'kind', 'degree', 'general_questions')

    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)

        self.fields['vote_start_date'].localize = True
        self.fields['vote_end_date'].localize = True
        self.fields['kind'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('kind', flat=True).order_by().distinct()])
        self.fields['degree'].widget.attrs['readonly'] = True

        if self.instance.general_contribution:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]

    def clean_degree(self):
        return self.instance.degree

    def save(self, *args, **kw):
        user = kw.pop("user")
        super(CourseForm, self).save(*args, **kw)
        self.instance.general_contribution.questionnaires = self.cleaned_data.get('general_questions')
        self.instance.last_modified_user = user
        self.instance.save()

    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        exclude.remove('semester') # allow checking against the missing attribute

        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)


class UserForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = UserProfile
        fields = ('title', 'first_name', 'last_name', 'email', 'delegates')

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)

        # fix generated form
        self.fields['delegates'].required = False
        self.fields['delegates'].queryset = UserProfile.objects.order_by('username')
        self.fields['delegates'].help_text = ""

        # load user fields
        self.fields['first_name'].initial = self.instance.first_name
        self.fields['last_name'].initial = self.instance.last_name
        self.fields['email'].initial = self.instance.email

    def save(self, *args, **kw):
        self.instance.first_name = self.cleaned_data.get('first_name')
        self.instance.last_name = self.cleaned_data.get('last_name')
        self.instance.email = self.cleaned_data.get('email')
        self.instance.save()

        super(UserForm, self).save(*args, **kw)
