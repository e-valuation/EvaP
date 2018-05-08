from datetime import datetime, timedelta
import logging

from django import forms
from django.conf import settings
from django.db.models import Q
from django.forms.widgets import CheckboxSelectMultiple
from django.utils.translation import ugettext_lazy as _
from evap.evaluation.forms import UserModelMultipleChoiceField
from evap.evaluation.models import Course, Questionnaire, Semester, UserProfile
from evap.evaluation.tools import date_to_datetime
from evap.staff.forms import ContributionForm

logger = logging.getLogger(__name__)


class CourseForm(forms.ModelForm):
    general_questions = forms.ModelMultipleChoiceField(queryset=None, widget=CheckboxSelectMultiple, label=_("Questions about the course"))
    semester = forms.ModelChoiceField(Semester.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())

    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'vote_start_datetime', 'vote_end_date', 'type', 'degrees', 'general_questions', 'semester')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['general_questions'].queryset = Questionnaire.objects.course_questionnaires().filter(
            (Q(staff_only=False) & Q(obsolete=False)) | Q(contributions__course=self.instance)).distinct()

        self.fields['vote_start_datetime'].localize = True
        self.fields['vote_end_date'].localize = True
        self.fields['degrees'].disabled = True
        self.fields['degrees'].help_text = ""

        if self.instance.general_contribution:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]

    def clean(self):
        super().clean()

        vote_start_datetime = self.cleaned_data.get('vote_start_datetime')
        vote_end_date = self.cleaned_data.get('vote_end_date')
        if vote_start_datetime and vote_end_date:
            if vote_start_datetime.date() > vote_end_date:
                self.add_error("vote_start_datetime", "")
                self.add_error("vote_end_date", _("The first day of evaluation must be before the last one."))

    def clean_vote_start_datetime(self):
        vote_start_datetime = self.cleaned_data.get('vote_start_datetime')
        if vote_start_datetime and vote_start_datetime < datetime.now():
            raise forms.ValidationError(_("The first day of evaluation must be in the future."))
        return vote_start_datetime

    def clean_vote_end_date(self):
        vote_end_date = self.cleaned_data.get('vote_end_date')

        # The actual deadline is EVALUATION_END_OFFSET_HOURS:00 AM of the day after vote_end_date.
        # Therefore an evaluation date 24h + EVALUATION_END_OFFSET_HOURS in the past would technically still be in the future.
        if vote_end_date and date_to_datetime(vote_end_date) + timedelta(hours=24 + settings.EVALUATION_END_OFFSET_HOURS) < datetime.now():
            raise forms.ValidationError(_("The last day of evaluation must be in the future."))
        return vote_end_date

    def save(self, *args, **kw):
        user = kw.pop("user")
        self.instance.last_modified_user = user
        super().save(*args, **kw)
        self.instance.general_contribution.questionnaires.set(self.cleaned_data.get('general_questions'))
        logger.info('Course "{}" (id {}) was edited by contributor {}.'.format(self.instance, self.instance.id, user.username))


class EditorContributionForm(ContributionForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.responsible:
            self.fields['responsibility'].disabled = True
            self.fields['contributor'].disabled = True
            self.fields['comment_visibility'].disabled = True

        self.fields['questionnaires'].queryset = Questionnaire.objects.contributor_questionnaires().filter(
            (Q(staff_only=False) & Q(obsolete=False)) | Q(contributions__course=self.course)).distinct()


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
