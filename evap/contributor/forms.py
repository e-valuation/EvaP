from datetime import datetime

from django import forms
from django.db.models import Q
from django.forms.widgets import CheckboxSelectMultiple
from django.utils.translation import gettext_lazy as _

from evap.evaluation.forms import UserModelChoiceField, UserModelMultipleChoiceField
from evap.evaluation.models import Course, Evaluation, Questionnaire, UserProfile
from evap.evaluation.tools import vote_end_datetime
from evap.staff.forms import ContributionForm


class EvaluationForm(forms.ModelForm):
    general_questionnaires = forms.ModelMultipleChoiceField(
        queryset=None, required=False, widget=CheckboxSelectMultiple, label=_("General questionnaires")
    )
    course = forms.ModelChoiceField(Course.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())
    name_de_field = forms.CharField(label=_("Name (German)"), disabled=True, required=False)
    name_en_field = forms.CharField(label=_("Name (English)"), disabled=True, required=False)

    class Meta:
        model = Evaluation
        fields = (
            "name_de_field",
            "name_en_field",
            "vote_start_datetime",
            "vote_end_date",
            "participants",
            "general_questionnaires",
            "course",
        )
        field_classes = {
            "participants": UserModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["name_de_field"].initial = self.instance.full_name_de
        self.fields["name_en_field"].initial = self.instance.full_name_en

        self.fields["general_questionnaires"].queryset = (
            Questionnaire.objects.general_questionnaires()
            .filter(Q(visibility=Questionnaire.Visibility.EDITORS) | Q(contributions__evaluation=self.instance))
            .distinct()
        )

        self.fields["vote_start_datetime"].localize = True
        self.fields["vote_end_date"].localize = True

        queryset = UserProfile.objects.exclude(is_active=False)
        if self.instance.pk is not None:
            queryset = (queryset | self.instance.participants.all()).distinct()
        self.fields["participants"].queryset = queryset

        if self.instance.general_contribution:
            self.fields["general_questionnaires"].initial = [
                q.pk for q in self.instance.general_contribution.questionnaires.all()
            ]

        if not self.instance.allow_editors_to_edit:
            for field in self._meta.fields:
                self.fields[field].disabled = True

    def clean(self):
        super().clean()

        vote_start_datetime = self.cleaned_data.get("vote_start_datetime")
        vote_end_date = self.cleaned_data.get("vote_end_date")
        if vote_start_datetime and vote_end_date and vote_start_datetime.date() > vote_end_date:
            self.add_error("vote_start_datetime", "")
            self.add_error("vote_end_date", _("The first day of evaluation must be before the last one."))

    def clean_vote_end_date(self):
        vote_end_date = self.cleaned_data.get("vote_end_date")

        # The actual deadline is EVALUATION_END_OFFSET_HOURS:00 AM of the day after vote_end_date.
        # Therefore an evaluation date 24h + EVALUATION_END_OFFSET_HOURS in the past would technically still be in the future.
        if vote_end_datetime(vote_end_date) < datetime.now():
            raise forms.ValidationError(_("The last day of evaluation must be in the future."))

        return vote_end_date

    def clean_general_questionnaires(self):
        # Ensure all locked questionnaires still have the same status (included or not)
        not_locked = []
        if self.cleaned_data.get("general_questionnaires"):
            not_locked = list(self.cleaned_data.get("general_questionnaires").filter(is_locked=False))

        locked = list(self.instance.general_contribution.questionnaires.filter(is_locked=True))

        if not not_locked + locked:
            self.add_error("general_questionnaires", _("At least one questionnaire must be selected."))

        return not_locked + locked

    def save(self, *args, **kw):
        evaluation = super().save(*args, **kw)
        evaluation.general_contribution.questionnaires.set(self.cleaned_data.get("general_questionnaires"))
        return evaluation


class EditorContributionForm(ContributionForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        existing_contributor_pk = self.instance.contributor.pk if self.instance.contributor else None

        self.fields["questionnaires"].queryset = (
            Questionnaire.objects.contributor_questionnaires()
            .filter(Q(visibility=Questionnaire.Visibility.EDITORS) | Q(contributions__evaluation=self.evaluation))
            .distinct()
        )
        self.fields["contributor"].queryset = UserProfile.objects.filter(
            (Q(is_active=True) & Q(is_proxy_user=False)) | Q(pk=existing_contributor_pk)
        )


class DelegateSelectionForm(forms.Form):
    delegate_to = UserModelChoiceField(
        label=_("Delegate to"), queryset=UserProfile.objects.exclude(is_active=False).exclude(is_proxy_user=True)
    )
