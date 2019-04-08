from datetime import datetime, timedelta
import logging

from django import forms
from django.conf import settings
from django.db.models import Q
from django.forms.widgets import CheckboxSelectMultiple
from django.utils.translation import ugettext_lazy as _
from evap.evaluation.forms import UserModelMultipleChoiceField, UserModelChoiceField
from evap.evaluation.models import Course, Evaluation, Questionnaire, UserProfile
from evap.evaluation.tools import date_to_datetime
from evap.staff.forms import ContributionForm

logger = logging.getLogger(__name__)


class EvaluationForm(forms.ModelForm):
    general_questionnaires = forms.ModelMultipleChoiceField(queryset=None, widget=CheckboxSelectMultiple, label=_("General questionnaires"))
    course = forms.ModelChoiceField(Course.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())
    name_de_field = forms.CharField(label=_("Name (German)"), disabled=True, required=False)
    name_en_field = forms.CharField(label=_("Name (English)"), disabled=True, required=False)

    class Meta:
        model = Evaluation
        fields = ('name_de_field', 'name_en_field', 'vote_start_datetime', 'vote_end_date', 'general_questionnaires', 'course')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['name_de_field'].initial = self.instance.full_name_de
        self.fields['name_en_field'].initial = self.instance.full_name_en

        self.fields['general_questionnaires'].queryset = Questionnaire.objects.general_questionnaires().filter(
            (Q(manager_only=False) & Q(obsolete=False)) | Q(contributions__evaluation=self.instance)).distinct()

        self.fields['vote_start_datetime'].localize = True
        self.fields['vote_end_date'].localize = True

        if self.instance.general_contribution:
            self.fields['general_questionnaires'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]

    def clean(self):
        super().clean()

        vote_start_datetime = self.cleaned_data.get('vote_start_datetime')
        vote_end_date = self.cleaned_data.get('vote_end_date')
        if vote_start_datetime and vote_end_date:
            if vote_start_datetime.date() > vote_end_date:
                self.add_error("vote_start_datetime", "")
                self.add_error("vote_end_date", _("The first day of evaluation must be before the last one."))

    def clean_vote_end_date(self):
        vote_end_date = self.cleaned_data.get('vote_end_date')

        # The actual deadline is EVALUATION_END_OFFSET_HOURS:00 AM of the day after vote_end_date.
        # Therefore an evaluation date 24h + EVALUATION_END_OFFSET_HOURS in the past would technically still be in the future.
        if vote_end_date and date_to_datetime(vote_end_date) + timedelta(hours=24 + settings.EVALUATION_END_OFFSET_HOURS) < datetime.now():
            raise forms.ValidationError(_("The last day of evaluation must be in the future."))
        return vote_end_date

    def save(self, *args, **kw):
        evaluation = super().save(*args, **kw)
        evaluation.general_contribution.questionnaires.set(self.cleaned_data.get('general_questionnaires'))
        return evaluation


class EditorContributionForm(ContributionForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['questionnaires'].queryset = Questionnaire.objects.contributor_questionnaires().filter(
            (Q(manager_only=False) & Q(obsolete=False)) | Q(contributions__evaluation=self.evaluation)).distinct()


class DelegatesForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('delegates',)
        field_classes = {
            'delegates': UserModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['delegates'].queryset = UserProfile.objects.exclude_inactive_users()

    def save(self, *args, **kw):
        super().save(*args, **kw)
        logger.info('User "{}" edited the settings.'.format(self.instance.username))


class DelegateSelectionForm(forms.Form):
    delegate_to = UserModelChoiceField(label=_("Delegate to"), queryset=UserProfile.objects.exclude_inactive_users())
