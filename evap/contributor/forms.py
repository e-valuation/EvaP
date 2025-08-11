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
    general_questionnaires: "forms.ModelMultipleChoiceField[Questionnaire]" = forms.ModelMultipleChoiceField(
        queryset=None, required=False, widget=CheckboxSelectMultiple, label=_("General questionnaires")
    )
    dropout_questionnaires: "forms.ModelMultipleChoiceField[Questionnaire]" = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=CheckboxSelectMultiple,
        label=_("Dropout questionnaires"),
    )
    course = forms.ModelChoiceField(Course.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())
    name_de_field = forms.CharField(label=_("Name (German)"), disabled=True, required=False)
    name_en_field = forms.CharField(label=_("Name (English)"), disabled=True, required=False)

    class Meta:
        model = Evaluation
        fields = (
            "name_de_field",
            "name_en_field",
            "main_language",
            "vote_start_datetime",
            "vote_end_date",
            "participants",
            "general_questionnaires",
            "dropout_questionnaires",
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
            .prefetch_related("questions")
        )
        self.fields["dropout_questionnaires"].queryset = (
            Questionnaire.objects.dropout_questionnaires()
            .filter(Q(visibility=Questionnaire.Visibility.EDITORS) | Q(contributions__evaluation=self.instance))
            .distinct()
            .prefetch_related("questions")
        )

        self.fields["vote_start_datetime"].localize = True
        self.fields["vote_end_date"].localize = True

        queryset = UserProfile.objects.exclude(is_active=False)
        if self.instance.pk is not None:
            queryset = (queryset | self.instance.participants.all()).distinct()
        self.fields["participants"].queryset = queryset

        if general_contribution := self.instance.general_contribution:
            self.fields["general_questionnaires"].initial = [
                q.pk for q in general_contribution.questionnaires.all() if q.is_general
            ]
            self.fields["dropout_questionnaires"].initial = [
                q.pk for q in general_contribution.questionnaires.all() if q.is_dropout
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

        # Ensure locked questionnaires cannot be deselected and only unlocked ones can be added
        selected_questionnaires = self.instance.general_contribution.questionnaires.filter(is_locked=True).distinct()
        selected_questionnaires |= self.cleaned_data.get("general_questionnaires").filter(is_locked=False)
        selected_questionnaires |= self.cleaned_data.get("dropout_questionnaires").filter(is_locked=False)

        self.cleaned_data.update(
            general_questionnaires=selected_questionnaires.exclude(type=Questionnaire.Type.DROPOUT),
            dropout_questionnaires=selected_questionnaires.filter(type=Questionnaire.Type.DROPOUT),
        )

        if not self.cleaned_data.get("general_questionnaires"):
            self.add_error("general_questionnaires", _("At least one questionnaire must be selected."))

    def clean_vote_end_date(self):
        vote_end_date = self.cleaned_data.get("vote_end_date")

        # The actual deadline is EVALUATION_END_OFFSET_HOURS:00 AM of the day after vote_end_date.
        # Therefore an evaluation date 24h + EVALUATION_END_OFFSET_HOURS in the past would technically still be in the future.
        if vote_end_datetime(vote_end_date) < datetime.now():
            raise forms.ValidationError(_("The last day of evaluation must be in the future."))

        return vote_end_date

    def clean_main_language(self):
        main_language = self.cleaned_data.get("main_language")
        if main_language == Evaluation.UNDECIDED_MAIN_LANGUAGE:
            self.add_error("main_language", _("You have to set a main language for this evaluation."))
        return main_language

    def save(self, *args, **kw):
        evaluation = super().save(*args, **kw)
        selected_questionnaires = self.cleaned_data.get("general_questionnaires") | self.cleaned_data.get(
            "dropout_questionnaires"
        )
        evaluation.general_contribution.questionnaires.set(selected_questionnaires)
        return evaluation


class EditorContributionForm(ContributionForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        existing_contributor_pk = self.instance.contributor.pk if self.instance.contributor else None

        self.fields["questionnaires"].queryset = (
            Questionnaire.objects.contributor_questionnaires()
            .filter(Q(visibility=Questionnaire.Visibility.EDITORS) | Q(contributions__evaluation=self.evaluation))
            .distinct()
            .prefetch_related("questions")
        )
        self.fields["contributor"].queryset = UserProfile.objects.filter(
            (Q(is_active=True) & Q(is_proxy_user=False)) | Q(pk=existing_contributor_pk)
        )


class DelegateSelectionForm(forms.Form):
    delegate_to = UserModelChoiceField(
        label=_("Delegate to"), queryset=UserProfile.objects.exclude(is_active=False).exclude(is_proxy_user=True)
    )
