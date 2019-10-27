import logging

from django import forms
from django.contrib.auth.models import Group
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.db.models import Q, Max
from django.forms.models import BaseInlineFormSet
from django.forms.widgets import CheckboxSelectMultiple
from django.http.request import QueryDict
from django.utils.text import normalize_newlines
from django.utils.translation import ugettext_lazy as _
from evap.evaluation.forms import UserModelChoiceField, UserModelMultipleChoiceField
from evap.evaluation.models import (Contribution, Course, CourseType, Degree, EmailTemplate, Evaluation, FaqQuestion,
                                    FaqSection, Question, Questionnaire, RatingAnswerCounter, Semester, TextAnswer,
                                    UserProfile)
from evap.evaluation.tools import date_to_datetime
from evap.results.views import (update_template_cache,
                                update_template_cache_of_published_evaluations_in_course)

logger = logging.getLogger(__name__)


def disable_all_fields(form):
    for field in form.fields.values():
        field.disabled = True


class ImportForm(forms.Form):
    vote_start_datetime = forms.DateTimeField(label=_("Start of evaluation"), localize=True, required=False)
    vote_end_date = forms.DateField(label=_("End of evaluation"), localize=True, required=False)

    excel_file = forms.FileField(label=_("Excel file"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.excel_file_required = False
        self.vote_dates_required = False

    def clean(self):
        if self.excel_file_required and self.cleaned_data['excel_file'] is None:
            raise ValidationError(_("Please select an Excel file."))
        if self.vote_dates_required:
            if self.cleaned_data['vote_start_datetime'] is None or self.cleaned_data['vote_end_date'] is None:
                raise ValidationError(_("Please enter an evaluation period."))


class UserImportForm(forms.Form):
    excel_file = forms.FileField(label=_("Excel file"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.excel_file_required = False

    def clean(self):
        if self.excel_file_required and self.cleaned_data['excel_file'] is None:
            raise ValidationError(_("Please select an Excel file."))


class EvaluationParticipantCopyForm(forms.Form):
    evaluation = forms.ModelChoiceField(Evaluation.objects.all(), empty_label='<empty>', required=False, label=_("Evaluation"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.evaluation_selection_required = False

        # Here we split the evaluations by semester and create supergroups for them. We also make sure to include an empty option.
        choices = [('', '<empty>')]
        for semester in Semester.objects.all():
            evaluation_choices = [(evaluation.pk, evaluation.full_name) for evaluation in Evaluation.objects.filter(course__semester=semester)]
            if evaluation_choices:
                choices += [(semester.name, evaluation_choices)]

        self.fields['evaluation'].choices = choices

    def clean(self):
        if self.evaluation_selection_required and self.cleaned_data['evaluation'] is None:
            raise ValidationError(_("Please select an evaluation from the dropdown menu."))


class UserBulkDeleteForm(forms.Form):
    username_file = forms.FileField(label=_("Username file"))


class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ("name_de", "name_en", "short_name_de", "short_name_en")

    def save(self, *args, **kwargs):
        semester = super().save(*args, **kwargs)
        if 'short_name_en' in self.changed_data or 'short_name_de' in self.changed_data:
            update_template_cache(semester.evaluations.filter(state="published"))
        return semester


class DegreeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = Degree
        fields = "__all__"

    def clean(self):
        super().clean()
        if self.cleaned_data.get('DELETE') and not self.instance.can_be_deleted_by_manager:
            raise SuspiciousOperation("Deleting degree not allowed")

    def save(self, *args, **kwargs):
        degree = super().save(*args, **kwargs)
        if "name_en" in self.changed_data or "name_de" in self.changed_data:
            update_template_cache(Evaluation.objects.filter(state="published", course__degrees__in=[degree]))
        return degree


class CourseTypeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = CourseType
        fields = "__all__"

    def clean(self):
        super().clean()
        if self.cleaned_data.get('DELETE') and not self.instance.can_be_deleted_by_manager:
            raise SuspiciousOperation("Deleting course type not allowed")

    def save(self, *args, **kwargs):
        course_type = super().save(*args, **kwargs)
        if "name_en" in self.changed_data or "name_de" in self.changed_data:
            update_template_cache(Evaluation.objects.filter(state="published", course__type=course_type))
        return course_type


class CourseTypeMergeSelectionForm(forms.Form):
    main_type = forms.ModelChoiceField(CourseType.objects.all())
    other_type = forms.ModelChoiceField(CourseType.objects.all())

    def clean(self):
        super().clean()
        if self.cleaned_data.get('main_type') == self.cleaned_data.get('other_type'):
            raise ValidationError(_("You must select two different course types."))


class CourseForm(forms.ModelForm):
    semester = forms.ModelChoiceField(Semester.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())
    last_modified_user_name = forms.CharField(label=_("Last modified by"), disabled=True, required=False)

    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'type', 'degrees', 'responsibles', 'is_graded', 'is_private', 'last_modified_time',
                  'last_modified_user_name', 'semester')
        field_classes = {
            'responsibles': UserModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['responsibles'].queryset = UserProfile.objects.exclude(is_active=False)
        if self.instance.pk:
            self.fields['responsibles'].queryset |= UserProfile.objects.filter(pk__in=[user.pk for user in self.instance.responsibles.all()])

        self.fields['last_modified_time'].disabled = True
        if self.instance.last_modified_user:
            self.fields['last_modified_user_name'].initial = self.instance.last_modified_user.full_name

        if not self.instance.can_be_edited_by_manager:
            disable_all_fields(self)

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


class EvaluationForm(forms.ModelForm):
    general_questionnaires = forms.ModelMultipleChoiceField(
        Questionnaire.objects.general_questionnaires().exclude(visibility=Questionnaire.HIDDEN),
        widget=CheckboxSelectMultiple,
        label=_("General questions")
    )
    last_modified_user_name = forms.CharField(label=_("Last modified by"), disabled=True, required=False)

    class Meta:
        model = Evaluation
        fields = ('course', 'name_de', 'name_en', 'weight', 'is_rewarded', 'is_midterm_evaluation',
                  'vote_start_datetime', 'vote_end_date', 'participants', 'general_questionnaires',
                  'last_modified_time', 'last_modified_user_name')
        localized_fields = ('vote_start_datetime', 'vote_end_date')
        field_classes = {
            'participants': UserModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        semester = kwargs.pop('semester', None)
        super().__init__(*args, **kwargs)
        self.fields['course'].queryset = Course.objects.filter(semester=semester)

        self.fields['general_questionnaires'].queryset = Questionnaire.objects.general_questionnaires().filter(
            Q(visibility=Questionnaire.MANAGERS) | Q(visibility=Questionnaire.EDITORS) | Q(contributions__evaluation=self.instance)).distinct()

        self.fields['participants'].queryset = UserProfile.objects.exclude(is_active=False)

        if self.instance.general_contribution:
            self.fields['general_questionnaires'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]

        self.fields['last_modified_time'].disabled = True
        if self.instance.last_modified_user:
            self.fields['last_modified_user_name'].initial = self.instance.last_modified_user.full_name

        if self.instance.state in ['in_evaluation', 'evaluated', 'reviewed']:
            self.fields['vote_start_datetime'].disabled = True

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
        participants = self.cleaned_data.get('participants')
        if self.instance.pk:
            voters = self.instance.voters.all()
            removed_voters = set(voters) - set(participants)
            if removed_voters:
                names = [str(user) for user in removed_voters]
                self.add_error("participants", _("Participants who already voted for the evaluation can't be removed: %s") % ", ".join(names))

        return participants

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        course = self.cleaned_data.get('course')
        if weight == 0 and not course.evaluations.exclude(pk=self.instance.pk).filter(weight__gt=0).exists():
            self.add_error("weight", _("At least one evaluation of the course must have a weight greater than 0."))
        return weight

    def clean(self):
        super().clean()
        vote_start_datetime = self.cleaned_data.get('vote_start_datetime')
        vote_end_date = self.cleaned_data.get('vote_end_date')
        if vote_start_datetime and vote_end_date:
            if vote_start_datetime.date() > vote_end_date:
                self.add_error("vote_start_datetime", "")
                self.add_error("vote_end_date", _("The first day of evaluation must be before the last one."))

    def save(self, *args, **kw):
        evaluation = super().save(*args, **kw)
        evaluation.general_contribution.questionnaires.set(self.cleaned_data.get('general_questionnaires'))
        if hasattr(self.instance, 'old_course'):
            if self.instance.old_course != evaluation.course:
                update_template_cache_of_published_evaluations_in_course(self.instance.old_course)
                update_template_cache_of_published_evaluations_in_course(evaluation.course)
        return evaluation


class SingleResultForm(forms.ModelForm):
    last_modified_time_2 = forms.DateTimeField(label=_("Last modified"), required=False, localize=True, disabled=True)
    last_modified_user_2 = forms.CharField(label=_("Last modified by"), required=False, disabled=True)
    event_date = forms.DateField(label=_("Event date"), localize=True)
    answer_1 = forms.IntegerField(label=_("# very good"), initial=0)
    answer_2 = forms.IntegerField(label=_("# good"), initial=0)
    answer_3 = forms.IntegerField(label=_("# neutral"), initial=0)
    answer_4 = forms.IntegerField(label=_("# bad"), initial=0)
    answer_5 = forms.IntegerField(label=_("# very bad"), initial=0)

    class Meta:
        model = Evaluation
        fields = ('course', 'name_de', 'name_en', 'weight', 'event_date', 'answer_1', 'answer_2', 'answer_3',
                  'answer_4', 'answer_5', 'last_modified_time_2', 'last_modified_user_2')

    def __init__(self, *args, **kwargs):
        semester = kwargs.pop('semester', None)
        super().__init__(*args, **kwargs)
        self.fields['course'].queryset = Course.objects.filter(semester=semester)

        self.fields['last_modified_time_2'].initial = self.instance.last_modified_time
        if self.instance.last_modified_user:
            self.fields['last_modified_user_2'].initial = self.instance.last_modified_user.full_name

        if self.instance.vote_start_datetime:
            self.fields['event_date'].initial = self.instance.vote_start_datetime

        if self.instance.pk and not self.instance.can_be_edited_by_manager:
            disable_all_fields(self)

        if self.instance.pk:
            for answer_counter in self.instance.ratinganswer_counters:
                self.fields['answer_{}'.format(answer_counter.answer)].initial = answer_counter.count
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
        user = kw.pop("user")
        self.instance.last_modified_user = user
        event_date = self.cleaned_data['event_date']
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
            count = self.cleaned_data['answer_' + str(i)]
            total_votes += count
            RatingAnswerCounter.objects.update_or_create(contribution=contribution, question=single_result_question, answer=i, defaults={'count': count})
        evaluation._participant_count = total_votes
        evaluation._voter_count = total_votes

        # change state to "reviewed"
        # works only for single_results so the evaluation and its contribution must be saved first
        evaluation.single_result_created()
        evaluation.save()

        if hasattr(self.instance, 'old_course'):
            if self.instance.old_course != evaluation.course:
                update_template_cache_of_published_evaluations_in_course(self.instance.old_course)
                update_template_cache_of_published_evaluations_in_course(evaluation.course)

        return evaluation


class ContributionForm(forms.ModelForm):
    contributor = UserModelChoiceField(queryset=UserProfile.objects.exclude(is_active=False).exclude(is_proxy_user=True))
    responsibility = forms.ChoiceField(widget=forms.RadioSelect(), choices=Contribution.RESPONSIBILITY_CHOICES)
    evaluation = forms.ModelChoiceField(Evaluation.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())
    questionnaires = forms.ModelMultipleChoiceField(
        Questionnaire.objects.contributor_questionnaires().exclude(visibility=Questionnaire.HIDDEN),
        required=False,
        widget=CheckboxSelectMultiple,
        label=_("Questionnaires")
    )
    does_not_contribute = forms.BooleanField(required=False, label=_("Does not contribute to evaluation"))

    class Meta:
        model = Contribution
        fields = ('evaluation', 'contributor', 'questionnaires', 'order', 'responsibility', 'textanswer_visibility', 'label')
        widgets = {'order': forms.HiddenInput(), 'textanswer_visibility': forms.RadioSelect(choices=Contribution.TEXTANSWER_VISIBILITY_CHOICES)}

    def __init__(self, *args, evaluation=None, **kwargs):
        self.evaluation = evaluation
        # work around https://code.djangoproject.com/ticket/25880
        if self.evaluation is None:
            assert 'instance' in kwargs
            self.evaluation = kwargs['instance'].evaluation

        super().__init__(*args, **kwargs)

        if self.instance.can_edit:
            self.fields['responsibility'].initial = Contribution.IS_EDITOR
        else:
            self.fields['responsibility'].initial = Contribution.IS_CONTRIBUTOR

        if self.instance.contributor:
            self.fields['contributor'].queryset |= UserProfile.objects.filter(pk=self.instance.contributor.pk)

        self.fields['questionnaires'].queryset = Questionnaire.objects.contributor_questionnaires().filter(
            Q(visibility=Questionnaire.MANAGERS) | Q(visibility=Questionnaire.EDITORS) | Q(contributions__evaluation=self.evaluation)).distinct()

        if self.instance.pk:
            self.fields['does_not_contribute'].initial = not self.instance.questionnaires.exists()

        if self.evaluation.pk and not self.evaluation.can_be_edited_by_manager:
            # form is used as read-only evaluation view
            disable_all_fields(self)

    def clean(self):
        if not self.cleaned_data.get('does_not_contribute') and not self.cleaned_data.get('questionnaires'):
            self.add_error('does_not_contribute', _("Select either this option or at least one questionnaire!"))

    def save(self, *args, **kwargs):
        responsibility = self.cleaned_data['responsibility']
        is_editor = responsibility == Contribution.IS_EDITOR
        self.instance.can_edit = is_editor
        return super().save(*args, **kwargs)


class EvaluationEmailForm(forms.Form):
    recipients = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple(), choices=EmailTemplate.EMAIL_RECIPIENTS, label=_("Send email to"))
    subject = forms.CharField(label=_("Subject"))
    body = forms.CharField(widget=forms.Textarea(), label=_("Message"))

    def __init__(self, *args, evaluation, export=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.template = EmailTemplate()
        self.evaluation = evaluation
        self.fields['subject'].required = not export
        self.fields['body'].required = not export

    def clean(self):
        self.recipient_groups = self.cleaned_data.get('recipients')

        if not self.recipient_groups:
            raise forms.ValidationError(_("No recipient selected. Choose at least one group of recipients."))

        return self.cleaned_data

    def email_addresses(self):
        recipients = self.template.recipient_list_for_evaluation(self.evaluation, self.recipient_groups, filter_users_in_cc=False)
        return set(user.email for user in recipients if user.email)

    def send(self, request):
        self.template.subject = self.cleaned_data.get('subject')
        self.template.body = self.cleaned_data.get('body')
        EmailTemplate.send_to_users_in_evaluations(self.template, [self.evaluation], self.recipient_groups, use_cc=True, request=request)


class RemindResponsibleForm(forms.Form):

    to = UserModelChoiceField(None, required=False, disabled=True, label=_("To"))
    cc = UserModelMultipleChoiceField(None, required=False, disabled=True, label=_("CC"))
    subject = forms.CharField(label=_("Subject"))
    body = forms.CharField(widget=forms.Textarea(), label=_("Message"))

    def __init__(self, *args, responsible, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['to'].initial = responsible.pk
        self.fields['to'].queryset = UserProfile.objects.filter(pk=responsible.pk)
        self.fields['cc'].initial = responsible.cc_users.all() | responsible.delegates.all()
        self.fields['cc'].queryset = responsible.cc_users.all() | responsible.delegates.all()

        self.template = EmailTemplate.objects.get(name=EmailTemplate.EDITOR_REVIEW_REMINDER)
        self.fields['subject'].initial = self.template.subject
        self.fields['body'].initial = self.template.body

    def send(self, request, evaluations):
        recipient = self.cleaned_data.get('to')
        self.template.subject = self.cleaned_data.get('subject')
        self.template.body = self.cleaned_data.get('body')
        subject_params = {}
        body_params = {'user': recipient, 'evaluations': evaluations}
        EmailTemplate.send_to_user(recipient, self.template, subject_params, body_params, use_cc=True, request=request)


class QuestionnaireForm(forms.ModelForm):
    class Meta:
        model = Questionnaire
        exclude = ()
        widgets = {'order': forms.HiddenInput()}

    def save(self, commit=True, force_highest_order=False, *args, **kwargs):
        # get instance that has all the changes from the form applied, dont write to database
        questionnaire_instance = super().save(commit=False, *args, **kwargs)

        if force_highest_order or 'type' in self.changed_data:
            highest_existing_order = Questionnaire.objects.filter(type=questionnaire_instance.type).aggregate(Max('order'))['order__max'] or -1
            questionnaire_instance.order = highest_existing_order + 1

        if commit:
            questionnaire_instance.save(*args, **kwargs)

        return questionnaire_instance


class AtLeastOneFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        count = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                count += 1

        if count < 1:
            raise forms.ValidationError(_('You must have at least one of these.'))


class ContributionFormSet(BaseInlineFormSet):
    def __init__(self, data=None, *args, **kwargs):
        data = self.handle_moved_contributors(data, **kwargs)
        super().__init__(data, *args, **kwargs)
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
            if 'contributor' not in form_with_errors.cleaned_data:
                continue
            for deleted_form in self.forms:
                if not deleted_form.cleaned_data or 'contributor' not in deleted_form.cleaned_data or not deleted_form.cleaned_data.get('DELETE'):
                    continue
                if not deleted_form.cleaned_data['contributor'] == form_with_errors.cleaned_data['contributor']:
                    continue
                form_with_errors.instance = deleted_form.instance
                # we modified the form, so we have to force re-validation
                form_with_errors.full_clean()

    def handle_moved_contributors(self, data, **kwargs):
        """
            Work around https://code.djangoproject.com/ticket/25139
            Basically, if the user assigns a contributor who already has a contribution to a new contribution,
            this moves the contributor (and all the data of the new form they got assigned to) back to the original contribution.
        """
        if data is None or 'instance' not in kwargs:
            return data

        evaluation = kwargs['instance']
        total_forms = int(data['contributions-TOTAL_FORMS'])
        for i in range(0, total_forms):
            prefix = "contributions-" + str(i) + "-"
            current_id = data.get(prefix + 'id', '')
            contributor = data.get(prefix + 'contributor', '')
            if contributor == '':
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
                other_id = data[other_prefix + 'id']
                if other_id == previous_id:
                    # swap all the data. the contribution's ids stay in place.
                    data2 = data.copy()
                    data = QueryDict(mutable=True)
                    for key, value in data2.lists():
                        if not key.endswith('-id'):
                            key = key.replace(prefix, '%temp%').replace(other_prefix, prefix).replace('%temp%', other_prefix)
                        data.setlist(key, value)
                    break
        return data

    def clean(self):
        self.handle_deleted_and_added_contributions()

        super().clean()

        found_contributor = set()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            contributor = form.cleaned_data.get('contributor')
            if contributor is None:
                raise forms.ValidationError(_('Please select the name of each added contributor. Remove empty rows if necessary.'))
            if contributor and contributor in found_contributor:
                raise forms.ValidationError(_('Duplicate contributor found. Each contributor should only be used once.'))
            elif contributor:
                found_contributor.add(contributor)


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"
        widgets = {
            'text_de': forms.Textarea(attrs={'rows': 2}),
            'text_en': forms.Textarea(attrs={'rows': 2})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["order"].widget = forms.HiddenInput()


class QuestionnairesAssignForm(forms.Form):
    def __init__(self, *args, course_types, **kwargs):
        super().__init__(*args, **kwargs)

        for course_type in course_types:
            self.fields[course_type.name] = forms.ModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.general_questionnaires().exclude(visibility=Questionnaire.HIDDEN))
        contributor_questionnaires = Questionnaire.objects.contributor_questionnaires().exclude(visibility=Questionnaire.HIDDEN)
        self.fields['All contributors'] = forms.ModelMultipleChoiceField(label=_('All contributors'), required=False, queryset=contributor_questionnaires)


class UserForm(forms.ModelForm):
    is_manager = forms.BooleanField(required=False, label=_("Manager"))
    is_grade_publisher = forms.BooleanField(required=False, label=_("Grade publisher"))
    is_reviewer = forms.BooleanField(required=False, label=_("Reviewer"))
    is_inactive = forms.BooleanField(required=False, label=_("Inactive"))
    evaluations_participating_in = forms.ModelMultipleChoiceField(None, required=False, label=_("Evaluations participating in (active semester)"))

    class Meta:
        model = UserProfile
        fields = ('username', 'title', 'first_name', 'last_name', 'email', 'delegates', 'cc_users', 'is_proxy_user')
        field_classes = {
            'delegates': UserModelMultipleChoiceField,
            'cc_users': UserModelMultipleChoiceField,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        evaluations_in_active_semester = Evaluation.objects.filter(course__semester=Semester.active_semester())
        excludes = [x.id for x in evaluations_in_active_semester if x.is_single_result]
        evaluations_in_active_semester = evaluations_in_active_semester.exclude(id__in=excludes)
        self.fields['evaluations_participating_in'].queryset = evaluations_in_active_semester
        if self.instance.pk:
            self.fields['evaluations_participating_in'].initial = evaluations_in_active_semester.filter(participants=self.instance)
            self.fields['is_manager'].initial = self.instance.is_manager
            self.fields['is_grade_publisher'].initial = self.instance.is_grade_publisher
            self.fields['is_reviewer'].initial = self.instance.is_reviewer
            self.fields['is_inactive'].initial = not self.instance.is_active

    def clean_username(self):
        username = self.cleaned_data.get('username')
        user_with_same_name = UserProfile.objects.filter(username__iexact=username)

        # make sure we don't take the instance itself into account
        if self.instance and self.instance.pk:
            user_with_same_name = user_with_same_name.exclude(pk=self.instance.pk)

        if user_with_same_name.exists():
            raise forms.ValidationError(_("A user with the username '%s' already exists") % username)
        return username.lower()

    def clean_evaluations_participating_in(self):
        evaluations_participating_in = self.cleaned_data.get('evaluations_participating_in')
        if self.instance.pk:
            evaluations_voted_for = self.instance.evaluations_voted_for.filter(course__semester=Semester.active_semester())
            removed_evaluations_voted_for = set(evaluations_voted_for) - set(evaluations_participating_in)
            if removed_evaluations_voted_for:
                names = [str(evaluation) for evaluation in removed_evaluations_voted_for]
                self.add_error("evaluations_participating_in", _("Evaluations for which the user already voted can't be removed: %s") % ", ".join(names))

        return evaluations_participating_in

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email is None:
            return

        user_with_same_email = UserProfile.objects.filter(email__iexact=email)

        # make sure we don't take the instance itself into account
        if self.instance and self.instance.pk:
            user_with_same_email = user_with_same_email.exclude(pk=self.instance.pk)

        if user_with_same_email.exists():
            raise forms.ValidationError(_("A user with the email '%s' already exists") % email)
        return email.lower()

    def save(self, *args, **kw):
        super().save(*args, **kw)
        new_evaluation_list = list(self.instance.evaluations_participating_in.exclude(course__semester=Semester.active_semester())) + list(self.cleaned_data.get('evaluations_participating_in'))
        self.instance.evaluations_participating_in.set(new_evaluation_list)

        manager_group = Group.objects.get(name="Manager")
        grade_publisher_group = Group.objects.get(name="Grade publisher")
        reviewer_group = Group.objects.get(name="Reviewer")
        if self.cleaned_data.get('is_manager'):
            self.instance.groups.add(manager_group)
        else:
            self.instance.groups.remove(manager_group)

        if self.cleaned_data.get('is_grade_publisher'):
            self.instance.groups.add(grade_publisher_group)
        else:
            self.instance.groups.remove(grade_publisher_group)

        if self.cleaned_data.get('is_reviewer') and not self.cleaned_data.get('is_manager'):
            self.instance.groups.add(reviewer_group)
        else:
            self.instance.groups.remove(reviewer_group)

        self.instance.is_active = not self.cleaned_data.get('is_inactive')

        self.instance.save()


class UserMergeSelectionForm(forms.Form):
    main_user = UserModelChoiceField(UserProfile.objects.all())
    other_user = UserModelChoiceField(UserProfile.objects.all())


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        exclude = ("name", )


class FaqSectionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = FaqSection
        exclude = ()


class FaqQuestionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = FaqQuestion
        exclude = ("section",)


class TextAnswerForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['original_answer'].disabled = "True"
        self.initial['original_answer'] = self.instance.original_answer or self.instance.answer

    class Meta:
        model = TextAnswer
        fields = ("answer", "original_answer",)

    def clean_original_answer(self):
        original_answer = normalize_newlines(self.cleaned_data.get('original_answer'))
        if original_answer == normalize_newlines(self.cleaned_data.get('answer')):
            return None
        return original_answer


class ExportSheetForm(forms.Form):
    def __init__(self, semester, *args, **kwargs):
        super(ExportSheetForm, self).__init__(*args, **kwargs)
        degrees = Degree.objects.filter(courses__semester=semester).distinct()
        degree_tuples = [(degree.pk, degree.name) for degree in degrees]
        self.fields['selected_degrees'] = forms.MultipleChoiceField(
            choices=degree_tuples,
            required=True,
            widget=forms.CheckboxSelectMultiple(),
            label=_("Degrees")
        )
        course_types = CourseType.objects.filter(courses__semester=semester).distinct()
        course_type_tuples = [(course_type.pk, course_type.name) for course_type in course_types]
        self.fields['selected_course_types'] = forms.MultipleChoiceField(
            choices=course_type_tuples,
            required=True,
            widget=forms.CheckboxSelectMultiple(),
            label=_("Course types")
        )
