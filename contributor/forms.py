import logging
import datetime

from django import forms
from django.forms.widgets import CheckboxSelectMultiple
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models import Q

from evap.evaluation.models import Course, UserProfile, Questionnaire, Semester
from evap.staff.forms import ContributionForm


logger = logging.getLogger(__name__)


class CourseForm(forms.ModelForm):
    general_questions = forms.ModelMultipleChoiceField(queryset=None, widget=CheckboxSelectMultiple, label=_("Questions about the course"))
    semester = forms.ModelChoiceField(Semester.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())

    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'vote_start_date', 'vote_end_date', 'type', 'degrees', 'general_questions', 'semester')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['general_questions'].queryset = Questionnaire.objects.filter(is_for_contributors=False).filter(
            (Q(staff_only=False) & Q(obsolete=False)) | Q(contributions__course=self.instance)).distinct()

        self.fields['vote_start_date'].localize = True
        self.fields['vote_end_date'].localize = True
        self.fields['degrees'].disabled = True
        self.fields['degrees'].help_text = ""

        if self.instance.general_contribution:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]

    def clean(self):
        super().clean()

        vote_start_date = self.cleaned_data.get('vote_start_date')
        vote_end_date = self.cleaned_data.get('vote_end_date')
        if vote_start_date and vote_end_date:
            if vote_start_date >= vote_end_date:
                raise ValidationError(_("The first day of evaluation must be before the last one."))

    def clean_vote_start_date(self):
        vote_start_date = self.cleaned_data.get('vote_start_date')
        if vote_start_date and vote_start_date < datetime.datetime.now():
            raise forms.ValidationError(_("The first day of evaluation must be in the future."))
        return vote_start_date

    def clean_vote_end_date(self):
        vote_end_date = self.cleaned_data.get('vote_end_date')
        if vote_end_date and vote_end_date < datetime.datetime.now():
            raise forms.ValidationError(_("The last day of evaluation must be in the future."))
        return vote_end_date

    def save(self, *args, **kw):
        user = kw.pop("user")
        self.instance.last_modified_user = user
        super().save(*args, **kw)
        self.instance.general_contribution.questionnaires = self.cleaned_data.get('general_questions')
        logger.info('Course "{}" (id {}) was edited by contributor {}.'.format(self.instance, self.instance.id, user.username))


class EditorContributionForm(ContributionForm):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        if self.instance.responsible:
            self.fields['responsibility'].disabled = True
            self.fields['contributor'].disabled = True
            self.fields['comment_visibility'].disabled = True

        self.fields['questionnaires'].queryset = Questionnaire.objects.filter(is_for_contributors=True).filter(
            (Q(staff_only=False) & Q(obsolete=False)) | Q(contributions__course=self.course)).distinct()


class DelegatesForm(forms.ModelForm):
    delegate_of = forms.ModelMultipleChoiceField(None, required=False, disabled=True)
    cc_user_of = forms.ModelMultipleChoiceField(None, required=False, disabled=True)

    class Meta:
        model = UserProfile
        fields = ('delegates', 'cc_users',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['cc_users'].disabled = True

        represented_users = self.instance.represented_users.all()
        self.fields['delegate_of'].queryset = represented_users
        self.fields['delegate_of'].initial = represented_users
        # work around https://code.djangoproject.com/ticket/25980
        self.fields['delegate_of'].initial = list(represented_users.values_list('pk', flat=True))

        ccing_users = self.instance.ccing_users.all()
        self.fields['cc_user_of'].queryset = ccing_users
        self.fields['cc_user_of'].initial = ccing_users
        # work around https://code.djangoproject.com/ticket/25980
        self.fields['cc_user_of'].initial = list(ccing_users.values_list('pk', flat=True))

    def save(self, *args, **kw):
        super().save(*args, **kw)
        logger.info('User "{}" edited the settings.'.format(self.instance.username))
