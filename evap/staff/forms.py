import logging
from collections.abc import Iterable

from django import forms
from django.contrib.auth.models import Group
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.forms.models import BaseInlineFormSet
from django.forms.widgets import CheckboxSelectMultiple
from django.http.request import QueryDict
from django.utils.text import normalize_newlines
from django.utils.translation import gettext_lazy as _

from evap.evaluation.forms import UserModelChoiceField, UserModelMultipleChoiceField
from evap.evaluation.models import (
    Contribution,
    Course,
    CourseType,
    Degree,
    EmailTemplate,
    Evaluation,
    FaqQuestion,
    FaqSection,
    Question,
    Questionnaire,
    RatingAnswerCounter,
    Semester,
    TextAnswer,
    UserProfile,
)
from evap.evaluation.tools import date_to_datetime
from evap.results.tools import STATES_WITH_RESULT_TEMPLATE_CACHING, STATES_WITH_RESULTS_CACHING, cache_results
from evap.results.views import update_template_cache, update_template_cache_of_published_evaluations_in_course
from evap.staff.tools import remove_user_from_represented_and_ccing_users
from evap.student.models import TextAnswerWarning

logger = logging.getLogger(__name__)


def disable_all_fields(form):
    for field in form.fields.values():
        field.disabled = True


class CharArrayField(forms.Field):
    hidden_widget = forms.MultipleHiddenInput
    widget = forms.SelectMultiple
    default_error_messages = {
        "invalid_list": _("Enter a list of values."),
    }

    def __init__(self, base_field, *, max_length=None, **kwargs):
        super().__init__(**kwargs)
        assert isinstance(base_field, forms.CharField)
        assert max_length is None

    def to_python(self, value):
        if not value:
            return []
        if not isinstance(value, Iterable):
            raise ValidationError(self.error_messages["invalid_list"], code="invalid_list")
        return [str(val) for val in value]

    def get_bound_field(self, form, field_name):
        return BoundCharArrayField(form, self, field_name)


class BoundCharArrayField(forms.BoundField):
    def as_widget(self, widget=None, attrs=None, only_initial=False):
        widget = widget or self.field.widget
        # Inject all current values as choices so they don’t get discarded
        if self.value():
            widget.choices = [(value, value) for value in self.value()]
        return super().as_widget(widget, attrs, only_initial)


class ModelWithImportNamesFormset(forms.BaseModelFormSet):
    """
    A form set which validates that import names are not duplicated
    """

    def clean(self):
        super().clean()
        import_names = set()
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            for import_name in form.cleaned_data.get("import_names", []):
                if import_name.lower() in import_names:
                    form.add_error(
                        "import_names",
                        _('Import name "{}" is duplicated. Import names are not case sensitive.').format(import_name),
                    )
                import_names.add(import_name.lower())


class ImportForm(forms.Form):
    use_required_attribute = False

    vote_start_datetime = forms.DateTimeField(label=_("Start of evaluation"), localize=True, required=False)
    vote_end_date = forms.DateField(label=_("End of evaluation"), localize=True, required=False)

    excel_file = forms.FileField(
        label=_("Excel file"),
        required=False,
        widget=forms.FileInput(attrs={"accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    )


class UserImportForm(forms.Form):
    use_required_attribute = False

    excel_file = forms.FileField(label=_("Excel file"), required=False)


class EvaluationParticipantCopyForm(forms.Form):
    evaluation = forms.ModelChoiceField(
        Evaluation.objects.all(), empty_label="<empty>", required=False, label=_("Evaluation")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.evaluation_selection_required = False

        # Here we split the evaluations by semester and create supergroups for them. We also make sure to include an empty option.
        choices = [("", "<empty>")]
        for semester in Semester.objects.all():
            evaluation_choices = [
                (evaluation.pk, evaluation.full_name)
                for evaluation in Evaluation.objects.filter(course__semester=semester)
            ]
            if evaluation_choices:
                choices += [(semester.name, evaluation_choices)]

        self.fields["evaluation"].choices = choices

    def clean(self):
        if self.evaluation_selection_required and self.cleaned_data["evaluation"] is None:
            raise ValidationError(_("Please select an evaluation from the dropdown menu."))


class UserBulkUpdateForm(forms.Form):
    use_required_attribute = False

    user_file = forms.FileField(label=_("User file"), required=False)


class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ("name_de", "name_en", "short_name_de", "short_name_en")

    def save(self, commit=True):
        semester = super().save(commit)
        if "short_name_en" in self.changed_data or "short_name_de" in self.changed_data:
            update_template_cache(semester.evaluations.filter(state__in=STATES_WITH_RESULT_TEMPLATE_CACHING))
        return semester


class DegreeForm(forms.ModelForm):
    class Meta:
        model = Degree
        fields = ("name_de", "name_en", "import_names", "order")
        field_classes = {
            "import_names": CharArrayField,
        }
        widgets = {
            "order": forms.HiddenInput(),
        }

    def clean(self):
        super().clean()
        if self.cleaned_data.get("DELETE") and not self.instance.can_be_deleted_by_manager:
            raise SuspiciousOperation("Deleting degree not allowed")

    def save(self, *args, **kwargs):
        degree = super().save(*args, **kwargs)
        if "name_en" in self.changed_data or "name_de" in self.changed_data:
            update_template_cache(
                Evaluation.objects.filter(state__in=STATES_WITH_RESULT_TEMPLATE_CACHING, course__degrees__in=[degree])
            )
        return degree


class CourseTypeForm(forms.ModelForm):
    class Meta:
        model = CourseType
        fields = ("name_de", "name_en", "import_names", "order")
        field_classes = {
            "import_names": CharArrayField,
        }
        widgets = {
            "order": forms.HiddenInput(),
        }

    def clean(self):
        super().clean()
        if self.cleaned_data.get("DELETE") and not self.instance.can_be_deleted_by_manager:
            raise SuspiciousOperation("Deleting course type not allowed")

    def save(self, *args, **kwargs):
        course_type = super().save(*args, **kwargs)
        if "name_en" in self.changed_data or "name_de" in self.changed_data:
            update_template_cache(
                Evaluation.objects.filter(state__in=STATES_WITH_RESULT_TEMPLATE_CACHING, course__type=course_type)
            )
        return course_type


class CourseTypeMergeSelectionForm(forms.Form):
    main_type = forms.ModelChoiceField(CourseType.objects.all())
    other_type = forms.ModelChoiceField(CourseType.objects.all())

    def clean(self):
        super().clean()
        if self.cleaned_data.get("main_type") == self.cleaned_data.get("other_type"):
            raise ValidationError(_("You must select two different course types."))


class CourseFormMixin:
    class Meta:
        model = Course
        fields = (
            "name_de",
            "name_en",
            "type",
            "degrees",
            "responsibles",
            "is_private",
            "semester",
        )
        field_classes = {
            "responsibles": UserModelMultipleChoiceField,
        }

    def _set_responsibles_queryset(self, existing_course=None):
        queryset = UserProfile.objects.exclude(is_active=False)
        if existing_course:
            queryset = (queryset | existing_course.responsibles.all()).distinct()
        self.fields["responsibles"].queryset = queryset

    def validate_unique(self):
        super().validate_unique()
        # name_xy and semester are unique together. This will be treated as a non-field-error since two
        # fields are involved. Since we only show the name_xy field to the user, assign that error to this
        # field. This hack is not documented, so it might be broken when you are reading this.
        for e in self.non_field_errors().as_data():
            if e.code == "unique_together" and "unique_check" in e.params:
                if "semester" in e.params["unique_check"]:
                    # The order of the fields is probably determined by the unique_together constraints in the Course class.
                    name_field = e.params["unique_check"][1]
                    self.add_error(name_field, e)


class CourseForm(CourseFormMixin, forms.ModelForm):  # type: ignore
    semester = forms.ModelChoiceField(Semester.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_responsibles_queryset(self.instance if self.instance.pk else None)
        if not self.instance.can_be_edited_by_manager:
            disable_all_fields(self)


class CourseCopyForm(CourseFormMixin, forms.ModelForm):  # type: ignore
    semester = forms.ModelChoiceField(Semester.objects.all())
    vote_start_datetime = forms.DateTimeField(label=_("Start of evaluations"), localize=True)
    vote_end_date = forms.DateField(label=_("Last day of evaluations"), localize=True)

    field_order = ["semester"]

    def __init__(self, data=None, *, instance: Course):
        self.old_course = instance
        opts = self._meta  # type: ignore
        initial = forms.models.model_to_dict(instance, opts.fields, opts.exclude)  # type: ignore
        super().__init__(data=data, initial=initial)
        self._set_responsibles_queryset(instance)

    # To ensure we don't forget about copying a relevant field, we explicitly list copied and ignored fields and test against that
    EVALUATION_COPIED_FIELDS = {
        "name_de",
        "name_en",
        "weight",
        "is_single_result",
        "is_rewarded",
        "is_midterm_evaluation",
        "allow_editors_to_edit",
        "wait_for_grade_upload_before_publishing",
    }

    EVALUATION_EXCLUDED_FIELDS = {
        "id",
        "course",
        "vote_start_datetime",
        "vote_end_date",
        "participants",
        "contributions",
        "state",
        "can_publish_text_results",
        "_participant_count",
        "_voter_count",
        "voters",
    }

    CONTRIBUTION_COPIED_FIELDS = {
        "contributor",
        "role",
        "textanswer_visibility",
        "label",
        "order",
    }

    CONTRIBUTION_EXCLUDED_FIELDS = {
        "id",
        "evaluation",
        "ratinganswercounter_set",
        "textanswer_set",
        "questionnaires",
    }

    @transaction.atomic()
    def save(self, commit=True):
        new_course: Course = super().save()
        # we need to create copies of evaluations and their participation as well
        for old_evaluation in self.old_course.evaluations.exclude(is_single_result=True):
            new_evaluation = Evaluation(
                **{field: getattr(old_evaluation, field) for field in self.EVALUATION_COPIED_FIELDS},
                can_publish_text_results=False,
                course=new_course,
                vote_start_datetime=self.cleaned_data["vote_start_datetime"],
                vote_end_date=self.cleaned_data["vote_end_date"],
            )
            new_evaluation.save()

            new_evaluation.contributions.all().delete()  # delete default general contribution
            for old_contribution in old_evaluation.contributions.all():
                new_contribution = Contribution(
                    **{field: getattr(old_contribution, field) for field in self.CONTRIBUTION_COPIED_FIELDS},
                    evaluation=new_evaluation,
                )
                new_contribution.save()
                new_contribution.questionnaires.set(old_contribution.questionnaires.all())

        return new_course


class EvaluationForm(forms.ModelForm):
    general_questionnaires = forms.ModelMultipleChoiceField(
        Questionnaire.objects.general_questionnaires().exclude(visibility=Questionnaire.Visibility.HIDDEN),
        widget=CheckboxSelectMultiple,
        label=_("General questions"),
    )

    class Meta:
        model = Evaluation
        fields = (
            "course",
            "name_de",
            "name_en",
            "weight",
            "allow_editors_to_edit",
            "is_rewarded",
            "is_midterm_evaluation",
            "wait_for_grade_upload_before_publishing",
            "vote_start_datetime",
            "vote_end_date",
            "participants",
            "general_questionnaires",
        )
        localized_fields = ("vote_start_datetime", "vote_end_date")
        field_classes = {
            "participants": UserModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        semester = kwargs.pop("semester", None)
        super().__init__(*args, **kwargs)
        self.fields["course"].queryset = Course.objects.filter(semester=semester)

        visible_questionnaires = Q(visibility__in=(Questionnaire.Visibility.MANAGERS, Questionnaire.Visibility.EDITORS))
        if self.instance.pk is not None:
            visible_questionnaires |= Q(contributions__evaluation=self.instance)
        self.fields["general_questionnaires"].queryset = (
            Questionnaire.objects.general_questionnaires().filter(visible_questionnaires).distinct()
        )

        queryset = UserProfile.objects.exclude(is_active=False)
        if self.instance.pk is not None:
            queryset = (queryset | self.instance.participants.all()).distinct()
        self.fields["participants"].queryset = queryset

        if self.instance.general_contribution:
            self.fields["general_questionnaires"].initial = [
                q.pk for q in self.instance.general_contribution.questionnaires.all()
            ]

        if Evaluation.State.IN_EVALUATION <= self.instance.state <= Evaluation.State.REVIEWED:
            self.fields["vote_start_datetime"].disabled = True

        if self.instance.pk and not self.instance.can_be_edited_by_manager:
            disable_all_fields(self)

        if self.instance.pk:
            self.instance.old_course = self.instance.course

    def validate_unique(self):
        super().validate_unique()
        # name_xy and course are unique together. This will be treated as a non-field-error since two
        # fields are involved. Since we only show the name_xy field to the user, assign that error to this
        # field. This hack is not documented, so it might be broken when you are reading this.
        for e in self.non_field_errors().as_data():
            if e.code == "unique_together" and "unique_check" in e.params:
                if "course" in e.params["unique_check"]:
                    # The order of the fields is probably determined by the unique_together constraints in the Evaluation class.
                    name_field = e.params["unique_check"][1]
                    self.add_error(name_field, e)

    def clean_participants(self):
        participants = self.cleaned_data.get("participants")
        if self.instance.pk:
            voters = self.instance.voters.all()
            removed_voters = set(voters) - set(participants)
            if removed_voters:
                names = [str(user) for user in removed_voters]
                self.add_error(
                    "participants",
                    _("Participants who already voted for the evaluation can't be removed: %s") % ", ".join(names),
                )

        return participants

    def clean_weight(self):
        weight = self.cleaned_data.get("weight")
        course = self.cleaned_data.get("course")
        if weight == 0 and not course.evaluations.exclude(pk=self.instance.pk).filter(weight__gt=0).exists():
            self.add_error("weight", _("At least one evaluation of the course must have a weight greater than 0."))
        return weight

    def clean(self):
        super().clean()

        vote_start_datetime = self.cleaned_data.get("vote_start_datetime")
        vote_end_date = self.cleaned_data.get("vote_end_date")
        if vote_start_datetime and vote_end_date and vote_start_datetime.date() > vote_end_date:
            self.add_error("vote_start_datetime", "")
            self.add_error("vote_end_date", _("The first day of evaluation must be before the last one."))

    def save(self, *args, **kw):
        evaluation = super().save(*args, **kw)
        selected_questionnaires = self.cleaned_data.get("general_questionnaires")
        removed_questionnaires = set(self.instance.general_contribution.questionnaires.all()) - set(
            selected_questionnaires
        )
        evaluation.general_contribution.remove_answers_to_questionnaires(removed_questionnaires)
        evaluation.general_contribution.questionnaires.set(selected_questionnaires)
        if hasattr(self.instance, "old_course"):
            if self.instance.old_course != evaluation.course:
                update_template_cache_of_published_evaluations_in_course(self.instance.old_course)
                update_template_cache_of_published_evaluations_in_course(evaluation.course)
        return evaluation


class EvaluationCopyForm(EvaluationForm):
    def __init__(self, data=None, instance=None):
        opts = self._meta
        initial = forms.models.model_to_dict(instance, opts.fields, opts.exclude)
        initial["general_questionnaires"] = instance.general_contribution.questionnaires.all()
        super().__init__(data=data, initial=initial, semester=instance.course.semester)


class SingleResultForm(forms.ModelForm):
    event_date = forms.DateField(label=_("Event date"), localize=True)
    answer_1 = forms.IntegerField(label=_("# very good"), initial=0)
    answer_2 = forms.IntegerField(label=_("# good"), initial=0)
    answer_3 = forms.IntegerField(label=_("# neutral"), initial=0)
    answer_4 = forms.IntegerField(label=_("# bad"), initial=0)
    answer_5 = forms.IntegerField(label=_("# very bad"), initial=0)

    class Meta:
        model = Evaluation
        fields = (
            "course",
            "name_de",
            "name_en",
            "weight",
            "event_date",
            "answer_1",
            "answer_2",
            "answer_3",
            "answer_4",
            "answer_5",
        )

    def __init__(self, *args, **kwargs):
        semester = kwargs.pop("semester", None)
        super().__init__(*args, **kwargs)
        self.fields["course"].queryset = Course.objects.filter(semester=semester)

        if self.instance.vote_start_datetime:
            self.fields["event_date"].initial = self.instance.vote_start_datetime

        if self.instance.pk and not self.instance.can_be_edited_by_manager:
            disable_all_fields(self)

        if self.instance.pk:
            for answer_counter in self.instance.ratinganswer_counters:
                self.fields[f"answer_{answer_counter.answer}"].initial = answer_counter.count
            self.instance.old_course = self.instance.course

    def validate_unique(self):
        super().validate_unique()
        # name_xy and course are unique together. This will be treated as a non-field-error since two
        # fields are involved. Since we only show the name_xy field to the user, assign that error to this
        # field. This hack is not documented, so it might be broken when you are reading this.
        for e in self.non_field_errors().as_data():
            if e.code == "unique_together" and "unique_check" in e.params:
                if "course" in e.params["unique_check"]:
                    # The order of the fields is probably determined by the unique_together constraints in the Evaluation class.
                    name_field = e.params["unique_check"][1]
                    self.add_error(name_field, e)

    def save(self, *args, **kw):
        event_date = self.cleaned_data["event_date"]
        self.instance.vote_start_datetime = date_to_datetime(event_date)
        self.instance.vote_end_date = event_date
        self.instance.is_single_result = True
        evaluation = super().save(*args, **kw)

        single_result_questionnaire = Questionnaire.single_result_questionnaire()
        single_result_question = single_result_questionnaire.questions.first()

        contribution, created = Contribution.objects.get_or_create(evaluation=evaluation, contributor=None)
        if created:
            contribution.questionnaires.add(single_result_questionnaire)
        contribution.save()

        # set answers
        contribution = Contribution.objects.get(evaluation=evaluation)
        total_votes = 0
        for i in range(1, 6):
            count = self.cleaned_data["answer_" + str(i)]
            total_votes += count
            RatingAnswerCounter.objects.update_or_create(
                contribution=contribution, question=single_result_question, answer=i, defaults={"count": count}
            )
        evaluation._participant_count = total_votes
        evaluation._voter_count = total_votes

        # change state to Evaluation.State.REVIEWED
        # works only for single_results so the evaluation and its contribution must be saved first
        evaluation.skip_review_single_result()
        evaluation.save()

        if hasattr(self.instance, "old_course"):
            if self.instance.old_course != evaluation.course:
                update_template_cache_of_published_evaluations_in_course(self.instance.old_course)
                update_template_cache_of_published_evaluations_in_course(evaluation.course)

        return evaluation


class ContributionForm(forms.ModelForm):
    contributor = UserModelChoiceField(queryset=UserProfile.objects.exclude(is_active=False))
    evaluation = forms.ModelChoiceField(
        Evaluation.objects.all(), disabled=True, required=False, widget=forms.HiddenInput()
    )
    questionnaires = forms.ModelMultipleChoiceField(
        Questionnaire.objects.contributor_questionnaires().exclude(visibility=Questionnaire.Visibility.HIDDEN),
        required=False,
        widget=CheckboxSelectMultiple,
        label=_("Questionnaires"),
    )
    does_not_contribute = forms.BooleanField(required=False, label=_("Add person without questions"))

    class Meta:
        model = Contribution
        fields = ("evaluation", "contributor", "questionnaires", "role", "textanswer_visibility", "label", "order")
        widgets = {
            "order": forms.HiddenInput(),
            # RadioSelects are necessary so each value gets a id_for_label, see #1769.
            "role": forms.RadioSelect(),
            "textanswer_visibility": forms.RadioSelect(),
        }

    def __init__(self, *args, evaluation=None, **kwargs):
        self.evaluation = evaluation
        # work around https://code.djangoproject.com/ticket/25880
        if self.evaluation is None:
            assert "instance" in kwargs
            self.evaluation = kwargs["instance"].evaluation

        super().__init__(*args, **kwargs)

        if self.instance.contributor:
            self.fields["contributor"].queryset |= UserProfile.objects.filter(pk=self.instance.contributor.pk)

        self.fields["questionnaires"].queryset = (
            Questionnaire.objects.contributor_questionnaires()
            .filter(
                Q(visibility=Questionnaire.Visibility.MANAGERS)
                | Q(visibility=Questionnaire.Visibility.EDITORS)
                | Q(contributions__evaluation=self.evaluation)
            )
            .distinct()
        )

        if self.instance.pk:
            self.fields["does_not_contribute"].initial = not self.instance.questionnaires.exists()

        if self.evaluation.pk and not self.evaluation.can_be_edited_by_manager:
            # form is used as read-only evaluation view
            disable_all_fields(self)

    def clean(self):
        if not self.cleaned_data.get("does_not_contribute") and not self.cleaned_data.get("questionnaires"):
            self.add_error("does_not_contribute", _("Select either this option or at least one questionnaire!"))

    @property
    def show_delete_button(self):
        if self.instance.pk is None:
            return True  # not stored in the DB. Required so temporary instances in the formset can be deleted.

        if not self.instance.ratinganswercounter_set.exists() and not self.instance.textanswer_set.exists():
            return True

        return False

    def save(self, *args, **kwargs):
        if self.instance.pk:
            selected_questionnaires = self.cleaned_data.get("questionnaires")
            removed_questionnaires = set(self.instance.questionnaires.all()) - set(selected_questionnaires)
            self.instance.remove_answers_to_questionnaires(removed_questionnaires)
        return super().save(*args, **kwargs)


class ContributionCopyForm(ContributionForm):
    def __init__(self, data=None, instance=None, evaluation=None, **kwargs):
        initial = None
        copied_instance = Contribution(evaluation=evaluation)
        if instance:
            opts = self._meta
            initial = forms.models.model_to_dict(instance, opts.fields, opts.exclude)
            del initial["evaluation"]
            initial["does_not_contribute"] = not instance.questionnaires.exists()
        super().__init__(data, initial=initial, instance=copied_instance, evaluation=evaluation, **kwargs)


class EvaluationEmailForm(forms.Form):
    recipients = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(), choices=EmailTemplate.Recipients.choices, label=_("Send email to")
    )
    subject = forms.CharField(label=_("Subject"))
    plain_content = forms.CharField(widget=forms.Textarea(), label=_("Plain Text"))
    html_content = forms.CharField(widget=forms.Textarea(), label=_("HTML"))

    def __init__(self, *args, evaluation, export=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.template = EmailTemplate()
        self.evaluation = evaluation
        self.recipient_groups = None
        self.fields["subject"].required = not export
        self.fields["plain_content"].required = not export
        self.fields["html_content"].required = False

    def clean(self):
        self.recipient_groups = self.cleaned_data.get("recipients")

        if not self.recipient_groups:
            raise forms.ValidationError(_("No recipient selected. Choose at least one group of recipients."))

        return self.cleaned_data

    def email_addresses(self):
        recipients = self.template.recipient_list_for_evaluation(
            self.evaluation, self.recipient_groups, filter_users_in_cc=False
        )
        return set(user.email for user in recipients if user.email)

    def send(self, request):
        self.template.subject = self.cleaned_data.get("subject")
        self.template.plain_content = self.cleaned_data.get("plain_content")
        self.template.html_content = self.cleaned_data.get("html_content")
        self.template.send_to_users_in_evaluations(
            [self.evaluation], self.recipient_groups, use_cc=True, request=request
        )


class RemindResponsibleForm(forms.Form):
    to = UserModelChoiceField(None, required=False, disabled=True, label=_("To"))
    cc = UserModelMultipleChoiceField(None, required=False, disabled=True, label=_("CC"))
    subject = forms.CharField(label=_("Subject"))
    plain_content = forms.CharField(widget=forms.Textarea(), label=_("Plain Text"))
    html_content = forms.CharField(widget=forms.Textarea(), label=_("HTML"))

    def __init__(self, *args, responsible, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["to"].initial = responsible.pk
        self.fields["to"].queryset = UserProfile.objects.filter(pk=responsible.pk)
        self.fields["cc"].initial = responsible.cc_users.all() | responsible.delegates.all()
        self.fields["cc"].queryset = responsible.cc_users.all() | responsible.delegates.all()

        self.template = EmailTemplate.objects.get(name=EmailTemplate.EDITOR_REVIEW_REMINDER)
        self.fields["subject"].initial = self.template.subject
        self.fields["plain_content"].initial = self.template.plain_content
        self.fields["html_content"].initial = self.template.html_content

    def send(self, request, evaluations):
        recipient = self.cleaned_data.get("to")
        self.template.subject = self.cleaned_data.get("subject")
        self.template.plain_content = self.cleaned_data.get("plain_content")
        self.template.html_content = self.cleaned_data.get("html_content")
        subject_params = {}
        body_params = {"user": recipient, "evaluations": evaluations}
        self.template.send_to_user(recipient, subject_params, body_params, use_cc=True, request=request)


class QuestionnaireForm(forms.ModelForm):
    class Meta:
        model = Questionnaire
        widgets = {"order": forms.HiddenInput()}
        fields = (
            "type",
            "name_de",
            "name_en",
            "description_de",
            "description_en",
            "public_name_de",
            "public_name_en",
            "teaser_de",
            "teaser_en",
            "order",
            "visibility",
            "is_locked",
        )

    def save(self, *args, commit=True, force_highest_order=False, **kwargs):
        # get instance that has all the changes from the form applied, dont write to database
        questionnaire_instance = super().save(commit=False, *args, **kwargs)

        if force_highest_order or "type" in self.changed_data:
            highest_existing_order = (
                Questionnaire.objects.filter(type=questionnaire_instance.type).aggregate(Max("order"))["order__max"]
                or -1
            )
            questionnaire_instance.order = highest_existing_order + 1

        if commit:
            questionnaire_instance.save(*args, **kwargs)

        return questionnaire_instance


class AtLeastOneFormset(BaseInlineFormSet):
    def clean(self):
        super().clean()
        count = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False):
                count += 1

        if count < 1:
            raise forms.ValidationError(_("You must have at least one of these."))


class ContributionFormset(BaseInlineFormSet):
    def __init__(self, data=None, **kwargs):
        data = self.handle_moved_contributors(data, **kwargs)
        super().__init__(data, **kwargs)
        self.queryset = self.instance.contributions.exclude(contributor=None)

    def handle_deleted_and_added_contributions(self):
        """
        If a contributor got removed and added in the same formset, django would usually complain
        when validating the added form, as it does not check whether the existing contribution was deleted.
        This method works around that.
        """
        for form_with_errors in self.forms:
            if not form_with_errors.errors:
                continue
            if "contributor" not in form_with_errors.cleaned_data:
                continue
            for deleted_form in self.forms:
                if (
                    not deleted_form.cleaned_data
                    or "contributor" not in deleted_form.cleaned_data
                    or not deleted_form.cleaned_data.get("DELETE")
                ):
                    continue
                if not deleted_form.cleaned_data["contributor"] == form_with_errors.cleaned_data["contributor"]:
                    continue
                form_with_errors.instance = deleted_form.instance
                # we modified the form, so we have to force re-validation
                form_with_errors.full_clean()

    @staticmethod
    def handle_moved_contributors(data, **kwargs):
        """
        Work around https://code.djangoproject.com/ticket/25139
        Basically, if the user assigns a contributor who already has a contribution to a new contribution,
        this moves the contributor (and all the data of the new form they got assigned to) back to the original contribution.
        """
        if data is None or "instance" not in kwargs:
            return data

        evaluation = kwargs["instance"]
        total_forms = int(data["contributions-TOTAL_FORMS"])
        for i in range(0, total_forms):
            prefix = "contributions-" + str(i) + "-"
            current_id = data.get(prefix + "id", "")
            contributor = data.get(prefix + "contributor", "")
            if contributor == "":
                continue
            # find the contribution that the contributor had before the user messed with it
            try:
                previous_id = str(Contribution.objects.get(contributor=contributor, evaluation=evaluation).id)
            except Contribution.DoesNotExist:
                continue

            if current_id == previous_id:
                continue

            # find the form with that previous contribution and then swap the contributions
            for j in range(0, total_forms):
                other_prefix = "contributions-" + str(j) + "-"
                other_id = data[other_prefix + "id"]
                if other_id == previous_id:
                    # swap all the data. the contribution's ids stay in place.
                    data2 = data.copy()
                    data = QueryDict(mutable=True)
                    for key, value in data2.lists():
                        if not key.endswith("-id"):
                            key = (
                                key.replace(prefix, "%temp%")
                                .replace(other_prefix, prefix)
                                .replace("%temp%", other_prefix)
                            )
                        data.setlist(key, value)
                    break
        return data

    def clean(self):
        self.handle_deleted_and_added_contributions()
        found_contributor = set()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            contributor = form.cleaned_data.get("contributor")
            if contributor is None:
                raise forms.ValidationError(
                    _("Please select the name of each added contributor. Remove empty rows if necessary.")
                )
            if contributor and contributor in found_contributor:
                raise forms.ValidationError(
                    _("Duplicate contributor ({}) found. Each contributor should only be used once.").format(
                        contributor.full_name
                    )
                )
            if contributor:
                found_contributor.add(contributor)
        super().clean()


class ContributionCopyFormset(ContributionFormset):
    def __init__(self, data, instance, new_instance):
        # First, pass the old evaluation instance to create a ContributionCopyForm for each contribution
        super().__init__(data, instance=instance, form_kwargs={"evaluation": new_instance})
        # Then, use the new evaluation instance as target for validation and saving purposes
        self.instance = new_instance

    def save(self, commit=True):
        # As the contained ContributionCopyForm have not-yet-saved instances,
        # they’d be skipped when saving the formset.
        # To circumvent this, explicitly note that all forms should be saved as new instance.
        self.save_as_new = True
        super().save(commit)


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ("order", "questionnaire", "text_de", "text_en", "type", "allows_additional_textanswers")
        widgets = {
            "text_de": forms.Textarea(attrs={"rows": 2}),
            "text_en": forms.Textarea(attrs={"rows": 2}),
            "order": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.type in [Question.TEXT, Question.HEADING]:
            self.fields["allows_additional_textanswers"].disabled = True

    def clean(self):
        super().clean()
        if self.cleaned_data.get("type") in [Question.TEXT, Question.HEADING]:
            self.cleaned_data["allows_additional_textanswers"] = False
        return self.cleaned_data


class QuestionnairesAssignForm(forms.Form):
    def __init__(self, *args, course_types, **kwargs):
        super().__init__(*args, **kwargs)

        for course_type in course_types:
            self.fields[course_type.name] = forms.ModelMultipleChoiceField(
                required=False,
                queryset=Questionnaire.objects.general_questionnaires().exclude(
                    visibility=Questionnaire.Visibility.HIDDEN
                ),
            )
        contributor_questionnaires = Questionnaire.objects.contributor_questionnaires().exclude(
            visibility=Questionnaire.Visibility.HIDDEN
        )
        self.fields["all-contributors"] = forms.ModelMultipleChoiceField(
            label=_("All contributors"), required=False, queryset=contributor_questionnaires
        )


class UserForm(forms.ModelForm):
    is_manager = forms.BooleanField(required=False, label=_("Manager"))
    is_grade_publisher = forms.BooleanField(required=False, label=_("Grade publisher"))
    is_reviewer = forms.BooleanField(required=False, label=_("Reviewer"))
    is_inactive = forms.BooleanField(required=False, label=_("Inactive"))
    evaluations_participating_in = forms.ModelMultipleChoiceField(
        None, required=False, label=_("Evaluations participating in (active semester)")
    )

    class Meta:
        model = UserProfile
        fields = ("title", "first_name", "last_name", "email", "delegates", "cc_users", "is_proxy_user")
        field_classes = {
            "delegates": UserModelMultipleChoiceField,
            "cc_users": UserModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        evaluations_in_active_semester = Evaluation.objects.filter(course__semester=Semester.active_semester())
        excludes = [x.id for x in evaluations_in_active_semester if x.is_single_result]
        evaluations_in_active_semester = evaluations_in_active_semester.exclude(id__in=excludes)
        self.fields["evaluations_participating_in"].queryset = evaluations_in_active_semester
        self.remove_messages = []
        if self.instance.pk:
            self.fields["evaluations_participating_in"].initial = evaluations_in_active_semester.filter(
                participants=self.instance
            )
            self.fields["is_manager"].initial = self.instance.is_manager
            self.fields["is_grade_publisher"].initial = self.instance.is_grade_publisher
            self.fields["is_reviewer"].initial = self.instance.is_reviewer
            self.fields["is_inactive"].initial = not self.instance.is_active

    def clean_evaluations_participating_in(self):
        evaluations_participating_in = self.cleaned_data.get("evaluations_participating_in")
        if self.instance.pk:
            evaluations_voted_for = self.instance.evaluations_voted_for.filter(
                course__semester=Semester.active_semester()
            )
            removed_evaluations_voted_for = set(evaluations_voted_for) - set(evaluations_participating_in)
            if removed_evaluations_voted_for:
                names = [str(evaluation) for evaluation in removed_evaluations_voted_for]
                self.add_error(
                    "evaluations_participating_in",
                    _("Evaluations for which the user already voted can't be removed: %s") % ", ".join(names),
                )

        return evaluations_participating_in

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email is None:
            return None

        user_with_same_email = UserProfile.objects.filter(email__iexact=email)

        # make sure we don't take the instance itself into account
        if self.instance and self.instance.pk:
            user_with_same_email = user_with_same_email.exclude(pk=self.instance.pk)

        if user_with_same_email.exists():
            raise forms.ValidationError(_("A user with the email '%s' already exists") % email)
        return email.lower()

    def save(self, *args, **kw):
        super().save(*args, **kw)
        new_evaluation_list = list(
            self.instance.evaluations_participating_in.exclude(course__semester=Semester.active_semester())
        ) + list(self.cleaned_data.get("evaluations_participating_in"))
        self.instance.evaluations_participating_in.set(new_evaluation_list)

        manager_group = Group.objects.get(name="Manager")
        grade_publisher_group = Group.objects.get(name="Grade publisher")
        reviewer_group = Group.objects.get(name="Reviewer")
        if self.cleaned_data.get("is_manager"):
            self.instance.groups.add(manager_group)
        else:
            self.instance.groups.remove(manager_group)

        if self.cleaned_data.get("is_grade_publisher"):
            self.instance.groups.add(grade_publisher_group)
        else:
            self.instance.groups.remove(grade_publisher_group)

        if self.cleaned_data.get("is_reviewer") and not self.cleaned_data.get("is_manager"):
            self.instance.groups.add(reviewer_group)
        else:
            self.instance.groups.remove(reviewer_group)

        self.instance.is_active = not self.cleaned_data.get("is_inactive")

        # remove instance from all other users' delegates and CC users if it is inactive
        self.remove_messages = (
            [] if self.instance.is_active else remove_user_from_represented_and_ccing_users(self.instance)
        )

        # refresh results cache
        if any(attribute in self.changed_data for attribute in ["first_name", "last_name", "title"]):
            evaluations = Evaluation.objects.filter(
                contributions__contributor=self.instance, state__in=STATES_WITH_RESULTS_CACHING
            ).distinct()
            for evaluation in evaluations:
                cache_results(evaluation)

        self.instance.save()


class UserMergeSelectionForm(forms.Form):
    main_user = UserModelChoiceField(UserProfile.objects.all())
    other_user = UserModelChoiceField(UserProfile.objects.all())


class UserEditSelectionForm(forms.Form):
    user = UserModelChoiceField(UserProfile.objects.all())


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ("subject", "plain_content", "html_content")


class FaqSectionForm(forms.ModelForm):
    class Meta:
        model = FaqSection
        fields = ("order", "title_de", "title_en")
        widgets = {
            "order": forms.HiddenInput(),
        }


class FaqQuestionForm(forms.ModelForm):
    class Meta:
        model = FaqQuestion
        fields = ("order", "question_de", "question_en", "answer_de", "answer_en")
        widgets = {
            "order": forms.HiddenInput(),
        }


class TextAnswerForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["original_answer"].disabled = "True"
        self.initial["original_answer"] = self.instance.original_answer or self.instance.answer

    class Meta:
        model = TextAnswer
        fields = (
            "answer",
            "original_answer",
        )

    def clean_original_answer(self):
        original_answer = normalize_newlines(self.cleaned_data.get("original_answer"))
        if original_answer == normalize_newlines(self.cleaned_data.get("answer")):
            return None
        return original_answer


class TextAnswerWarningForm(forms.ModelForm):
    class Meta:
        model = TextAnswerWarning
        fields = ("warning_text_de", "warning_text_en", "trigger_strings", "order")
        field_classes = {
            "trigger_strings": CharArrayField,
        }
        widgets = {
            "warning_text_de": forms.Textarea(attrs={"rows": 5}),
            "warning_text_en": forms.Textarea(attrs={"rows": 5}),
            "order": forms.HiddenInput(),
        }


class ExportSheetForm(forms.Form):
    def __init__(self, semester, *args, **kwargs):
        super().__init__(*args, **kwargs)
        degrees = Degree.objects.filter(courses__semester=semester).distinct()
        degree_tuples = [(degree.pk, degree.name) for degree in degrees]
        self.fields["selected_degrees"] = forms.MultipleChoiceField(
            choices=degree_tuples, required=True, widget=forms.CheckboxSelectMultiple(), label=_("Degrees")
        )
        course_types = CourseType.objects.filter(courses__semester=semester).distinct()
        course_type_tuples = [(course_type.pk, course_type.name) for course_type in course_types]
        self.fields["selected_course_types"] = forms.MultipleChoiceField(
            choices=course_type_tuples, required=True, widget=forms.CheckboxSelectMultiple(), label=_("Course types")
        )
