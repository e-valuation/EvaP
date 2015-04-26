from django import forms
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import Course, UserProfile, Questionnaire
from evap.evaluation.forms import BootstrapMixin, QuestionnaireMultipleChoiceField
from evap.staff.forms import ContributionFormSet

import datetime


class CourseForm(forms.ModelForm, BootstrapMixin):
    general_questions = QuestionnaireMultipleChoiceField(Questionnaire.objects.filter(is_for_contributors=False, obsolete=False), label=_("General questions"))

    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'vote_start_date', 'vote_end_date', 'type', 'degrees', 'general_questions')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['vote_start_date'].localize = True
        self.fields['vote_end_date'].localize = True
        self.fields['type'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('type', flat=True).order_by().distinct()])
        self.fields['degrees'].widget.attrs['disabled'] = "true"
        self.fields['degrees'].help_text = ""

        if self.instance.general_contribution:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]

    def clean_degree(self):
        return self.instance.degree

    def clean_vote_start_date(self):
        vote_start_date = self.cleaned_data.get('vote_start_date')
        if vote_start_date and vote_start_date < datetime.date.today():
            raise forms.ValidationError(_("The first day of evaluation must be in the future."))
        return vote_start_date

    def clean_vote_end_date(self):
        vote_end_date = self.cleaned_data.get('vote_end_date')
        if vote_end_date and vote_end_date < datetime.date.today():
            raise forms.ValidationError(_("The last day of evaluation must be in the future."))
        return vote_end_date

    def save(self, *args, **kw):
        user = kw.pop("user")
        super().save(*args, **kw)
        self.instance.general_contribution.questionnaires = self.cleaned_data.get('general_questions')
        self.instance.last_modified_user = user
        self.instance.save()

    def validate_unique(self):
        # see staff.forms.CourseForm for an explanation
        exclude = self._get_validation_exclusions()
        exclude.remove('semester')

        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)


class EditorContributionFormSet(ContributionFormSet):
    """
        A ContributionFormSet that protects againt POST hacks
        by always re-setting the responsible.
    """
    def clean(self):
        for form in self.forms:
            contribution = form.instance
            if contribution.responsible:
                contribution.contributor = contribution.course.responsible_contributor
        super().clean()


class UserForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = UserProfile
        fields = ('title', 'first_name', 'last_name', 'email', 'delegates')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

        super().save(*args, **kw)
