import logging

from django import forms
from django.db.models import Q
from django.core.exceptions import SuspiciousOperation
from django.forms.models import BaseInlineFormSet
from django.utils.translation import ugettext_lazy as _
from django.utils.text import normalize_newlines
from django.http.request import QueryDict
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group

from evap.evaluation.forms import BootstrapMixin, QuestionnaireMultipleChoiceField
from evap.evaluation.models import Contribution, Course, Question, Questionnaire, Semester, UserProfile, FaqSection, \
                                   FaqQuestion, EmailTemplate, TextAnswer, Degree, RatingAnswerCounter, CourseType
from evap.staff.fields import ToolTipModelMultipleChoiceField


logger = logging.getLogger(__name__)


def disable_all_fields(form):
    for field in form.fields.values():
        field.disabled = True


class ImportForm(forms.Form, BootstrapMixin):
    vote_start_date = forms.DateField(label=_("First day of evaluation"), localize=True)
    vote_end_date = forms.DateField(label=_("Last day of evaluation"), localize=True)

    excel_file = forms.FileField(label=_("Excel file"))


class UserImportForm(forms.Form, BootstrapMixin):
    excel_file = forms.FileField(label=_("Excel file"))


class UserBulkDeleteForm(forms.Form, BootstrapMixin):
    username_file = forms.FileField(label=_("Username file"))


class SemesterForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Semester
        fields = ("name_de", "name_en")


class DegreeForm(forms.ModelForm, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["name_de"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["name_en"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = Degree
        fields = "__all__"

    def clean(self):
        super().clean()
        if self.cleaned_data.get('DELETE') and not self.instance.can_staff_delete:
            raise SuspiciousOperation("Deleting degree not allowed")


class CourseTypeForm(forms.ModelForm, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["name_de"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["name_en"].widget = forms.TextInput(attrs={'class': 'form-control'})

    class Meta:
        model = CourseType
        fields = "__all__"

    def clean(self):
        super().clean()
        if self.cleaned_data.get('DELETE') and not self.instance.can_staff_delete:
            raise SuspiciousOperation("Deleting course type not allowed")


class CourseTypeMergeSelectionForm(forms.Form, BootstrapMixin):
    main_type = forms.ModelChoiceField(CourseType.objects.all())
    other_type = forms.ModelChoiceField(CourseType.objects.all())

    def clean(self):
        super().clean()
        if self.cleaned_data.get('main_type') == self.cleaned_data.get('other_type'):
            raise ValidationError(_("You must select two different course types."))


class CourseForm(forms.ModelForm, BootstrapMixin):
    general_questions = QuestionnaireMultipleChoiceField(Questionnaire.objects.filter(is_for_contributors=False, obsolete=False), label=_("General questions"))
    semester = forms.ModelChoiceField(Semester.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())

    # the following field is needed, because the auto_now=True for last_modified_time makes the corresponding field
    # uneditable and so it can't be displayed in the model form
    # see https://docs.djangoproject.com/en/dev/ref/models/fields/#datefield for details
    last_modified_time_2 = forms.DateTimeField(label=_("Last modified"), required=False, localize=True, disabled=True)
    # last_modified_user would usually get a select widget but should here be displayed as a readonly CharField instead
    last_modified_user_2 = forms.CharField(label=_("Last modified by"), required=False, disabled=True)

    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'type', 'degrees', 'is_graded', 'is_private', 'is_required_for_reward', 'vote_start_date',
                  'vote_end_date', 'participants', 'general_questions', 'last_modified_time_2', 'last_modified_user_2', 'semester')
        localized_fields = ('vote_start_date', 'vote_end_date')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['general_questions'].queryset = Questionnaire.objects.filter(is_for_contributors=False).filter(
            Q(obsolete=False) | Q(contributions__course=self.instance)).distinct()

        if self.instance.general_contribution:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]

        self.fields['last_modified_time_2'].initial = self.instance.last_modified_time
        if self.instance.last_modified_user:
            self.fields['last_modified_user_2'].initial = self.instance.last_modified_user.full_name

        if self.instance.state in ['in_evaluation', 'evaluated', 'reviewed']:
            self.fields['vote_start_date'].disabled = True

        if not self.instance.can_staff_edit:
            # form is used as read-only course view
            disable_all_fields(self)

    def clean(self):
        super().clean()
        vote_start_date = self.cleaned_data.get('vote_start_date')
        vote_end_date = self.cleaned_data.get('vote_end_date')
        if vote_start_date and vote_end_date:
            if vote_start_date >= vote_end_date:
                raise ValidationError(_("The first day of evaluation must be before the last one."))

    def save(self, user, *args, **kw):
        self.instance.last_modified_user = user
        super().save(*args, **kw)
        self.instance.general_contribution.questionnaires = self.cleaned_data.get('general_questions')
        logger.info('Course "{}" (id {}) was edited by staff member {}.'.format(self.instance, self.instance.id, user.username))


class SingleResultForm(forms.ModelForm, BootstrapMixin):
    semester = forms.ModelChoiceField(Semester.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())
    last_modified_time_2 = forms.DateTimeField(label=_("Last modified"), required=False, localize=True, disabled=True)
    last_modified_user_2 = forms.CharField(label=_("Last modified by"), required=False, disabled=True)
    event_date = forms.DateField(label=_("Event date"), localize=True)
    responsible = forms.ModelChoiceField(label=_("Responsible"), queryset=UserProfile.objects.all())
    answer_1 = forms.IntegerField(label=_("# very good"), initial=0)
    answer_2 = forms.IntegerField(label=_("# good"), initial=0)
    answer_3 = forms.IntegerField(label=_("# neutral"), initial=0)
    answer_4 = forms.IntegerField(label=_("# bad"), initial=0)
    answer_5 = forms.IntegerField(label=_("# very bad"), initial=0)

    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'type', 'degrees', 'event_date', 'responsible', 'answer_1', 'answer_2', 'answer_3', 'answer_4', 'answer_5',
                 'last_modified_time_2', 'last_modified_user_2', 'semester')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['last_modified_time_2'].initial = self.instance.last_modified_time
        if self.instance.last_modified_user:
            self.fields['last_modified_user_2'].initial = self.instance.last_modified_user.full_name

        if self.instance.vote_start_date:
            self.fields['event_date'].initial = self.instance.vote_start_date

        if not self.instance.can_staff_edit:
            disable_all_fields(self)

        if self.instance.pk:
            self.fields['responsible'].initial = self.instance.responsible_contributor
            answer_counts = dict()
            for answer_counter in self.instance.ratinganswer_counters:
                answer_counts[answer_counter.answer] = answer_counter.count
            for i in range(1, 6):
                self.fields['answer_' + str(i)].initial = answer_counts[i]

    def save(self, *args, **kw):
        user = kw.pop("user")
        self.instance.last_modified_user = user
        self.instance.vote_start_date = self.cleaned_data['event_date']
        self.instance.vote_end_date = self.cleaned_data['event_date']
        self.instance.is_graded = False
        super().save(*args, **kw)

        single_result_questionnaire = Questionnaire.get_single_result_questionnaire()
        single_result_question = single_result_questionnaire.question_set.first()

        if not Contribution.objects.filter(course=self.instance, responsible=True).exists():
            contribution = Contribution(course=self.instance, contributor=self.cleaned_data['responsible'], responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
            contribution.save()
            contribution.questionnaires.add(single_result_questionnaire)

        # set answers
        contribution = Contribution.objects.get(course=self.instance, responsible=True)
        total_votes = 0
        for i in range(1, 6):
            count = self.cleaned_data['answer_' + str(i)]
            total_votes += count
            RatingAnswerCounter.objects.update_or_create(contribution=contribution, question=single_result_question, answer=i, defaults={'count': count})
        self.instance._participant_count = total_votes
        self.instance._voter_count = total_votes

        # change state to "reviewed"
        # works only for single_results so the course and its contribution must be saved first
        self.instance.single_result_created()
        self.instance.save()


class ContributionForm(forms.ModelForm, BootstrapMixin):
    responsibility = forms.ChoiceField(widget=forms.RadioSelect(), choices=Contribution.RESPONSIBILITY_CHOICES)
    course = forms.ModelChoiceField(Course.objects.all(), disabled=True, required=False, widget=forms.HiddenInput())
    questionnaires = QuestionnaireMultipleChoiceField(Questionnaire.objects.filter(is_for_contributors=True, obsolete=False), label=_("Questionnaires"))

    class Meta:
        model = Contribution
        fields = ('course', 'contributor', 'questionnaires', 'order', 'responsibility', 'comment_visibility', 'label')
        widgets = {'order': forms.HiddenInput(), 'comment_visibility': forms.RadioSelect(choices=Contribution.COMMENT_VISIBILITY_CHOICES)}

    def __init__(self, *args, **kwargs):
        # work around https://code.djangoproject.com/ticket/25880
        self.course = kwargs.pop('course', None)
        if self.course is None:
            assert 'instance' in kwargs
            self.course = kwargs['instance'].course

        super().__init__(*args, **kwargs)

        self.fields['contributor'].widget.attrs['class'] = 'form-control'
        self.fields['label'].widget.attrs['class'] = 'form-control'

        if self.instance.responsible:
            self.fields['responsibility'].initial = Contribution.IS_RESPONSIBLE
        elif self.instance.can_edit:
            self.fields['responsibility'].initial = Contribution.IS_EDITOR
        else:
            self.fields['responsibility'].initial = Contribution.IS_CONTRIBUTOR

        self.fields['questionnaires'].queryset = Questionnaire.objects.filter(is_for_contributors=True).filter(
            Q(obsolete=False) | Q(contributions__course=self.course)).distinct()

        if not self.course.can_staff_edit:
            # form is used as read-only course view
            disable_all_fields(self)

    def save(self, *args, **kwargs):
        responsibility = self.cleaned_data['responsibility']
        is_responsible = responsibility == Contribution.IS_RESPONSIBLE
        is_editor = responsibility == Contribution.IS_EDITOR
        self.instance.responsible = is_responsible
        self.instance.can_edit = is_responsible or is_editor
        if is_responsible:
            self.instance.comment_visibility = Contribution.ALL_COMMENTS
        return super().save(*args, **kwargs)


class CourseEmailForm(forms.Form, BootstrapMixin):
    recipients = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple(), choices=EmailTemplate.EMAIL_RECIPIENTS, label=_("Send email to"))
    subject = forms.CharField(label=_("Subject"))
    body = forms.CharField(widget=forms.Textarea(), label=_("Message"))

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance')
        self.export = kwargs.pop('export', False)
        self.template = EmailTemplate()
        super().__init__(*args, **kwargs)
        self.fields['subject'].required = not self.export
        self.fields['body'].required = not self.export

    def clean(self):
        self.recipient_groups = self.cleaned_data.get('recipients')

        if not self.recipient_groups:
            raise forms.ValidationError(_("No recipient selected. Choose at least one group of recipients."))

        return self.cleaned_data

    def email_addresses(self):
        recipients = self.template.recipient_list_for_course(self.instance, self.recipient_groups, filter_users_in_cc=False)
        return set(user.email for user in recipients if user.email)

    def send(self):
        self.template.subject = self.cleaned_data.get('subject')
        self.template.body = self.cleaned_data.get('body')
        EmailTemplate.send_to_users_in_courses(self.template, [self.instance], self.recipient_groups, use_cc=True)


class QuestionnaireForm(forms.ModelForm, BootstrapMixin):

    class Meta:
        model = Questionnaire
        exclude = ()
        widgets = {'index': forms.HiddenInput()}


class AtLeastOneFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        count = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                count += 1

        if count < 1:
            raise forms.ValidationError(_('You must have at least one of these.'))


class ContributionFormSet(AtLeastOneFormSet):
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
            for deleted_form in self.forms:
                if not deleted_form.cleaned_data or not deleted_form.cleaned_data.get('DELETE'):
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

        course = kwargs['instance']
        total_forms = int(data['contributions-TOTAL_FORMS'])
        for i in range(0, total_forms):
            prefix = "contributions-" + str(i) + "-"
            current_id = data.get(prefix + 'id', '')
            contributor = data.get(prefix + 'contributor', '')
            if contributor == '':
                continue
            # find the contribution that the contributor had before the user messed with it
            try:
                previous_id = str(Contribution.objects.get(contributor=contributor, course=course).id)
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
        count_responsible = 0
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

            if form.cleaned_data.get('responsibility') == 'RESPONSIBLE':
                count_responsible += 1

        if count_responsible < 1:
            raise forms.ValidationError(_('No responsible contributor found. Each course must have exactly one responsible contributor.'))
        elif count_responsible > 1:
            raise forms.ValidationError(_('Too many responsible contributors found. Each course must have exactly one responsible contributor.'))


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["order"].widget = forms.HiddenInput()
        self.fields['text_de'].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields['text_en'].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields['type'].widget.attrs['class'] = 'form-control'


class QuestionnairesAssignForm(forms.Form, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        course_types = kwargs.pop('course_types')
        super().__init__(*args, **kwargs)

        for course_type in course_types:
            self.fields[course_type.name] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False, is_for_contributors=False))
        contributor_questionnaires = Questionnaire.objects.filter(obsolete=False, is_for_contributors=True)
        self.fields['Responsible contributor'] = ToolTipModelMultipleChoiceField(label=_('Responsible contributor'), required=False, queryset=contributor_questionnaires)


class UserForm(forms.ModelForm, BootstrapMixin):
    is_staff = forms.BooleanField(required=False, label=_("Staff user"))
    is_grade_user = forms.BooleanField(required=False, label=_("Grade user"))
    courses_participating_in = forms.ModelMultipleChoiceField(None, required=False, label=_("Courses participating in (active semester)"))

    class Meta:
        model = UserProfile
        fields = ('username', 'title', 'first_name', 'last_name', 'email', 'delegates', 'cc_users')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        courses_in_active_semester = Course.objects.filter(semester=Semester.active_semester())
        excludes = [x.id for x in courses_in_active_semester if x.is_single_result]
        courses_in_active_semester = courses_in_active_semester.exclude(id__in=excludes)
        self.fields['courses_participating_in'].queryset = courses_in_active_semester
        if self.instance.pk:
            self.fields['courses_participating_in'].initial = courses_in_active_semester.filter(participants=self.instance)
            self.fields['is_staff'].initial = self.instance.is_staff
            self.fields['is_grade_user'].initial = self.instance.is_grade_publisher

    def clean_username(self):
        username = self.cleaned_data.get('username')
        user_with_same_name = UserProfile.objects.filter(username__iexact=username)

        # make sure we don't take the instance itself into account
        if self.instance and self.instance.pk:
            user_with_same_name = user_with_same_name.exclude(pk=self.instance.pk)

        if user_with_same_name.exists():
            raise forms.ValidationError(_("A user with the username '%s' already exists") % username)
        return username.lower()

    def clean_email(self):
        email = self.cleaned_data.get('email')
        user_with_same_email = UserProfile.objects.filter(email__iexact=email)

        # make sure we don't take the instance itself into account
        if self.instance and self.instance.pk:
            user_with_same_email = user_with_same_email.exclude(pk=self.instance.pk)

        if user_with_same_email.exists():
            raise forms.ValidationError(_("A user with the email '%s' already exists") % email)
        return email.lower()

    def save(self, *args, **kw):
        super().save(*args, **kw)
        self.instance.courses_participating_in = list(self.instance.courses_participating_in.exclude(semester=Semester.active_semester())) + list(self.cleaned_data.get('courses_participating_in'))

        staff_group = Group.objects.get(name="Staff")
        grade_user_group = Group.objects.get(name="Grade publisher")
        if self.cleaned_data.get('is_staff'):
            self.instance.groups.add(staff_group)
        else:
            self.instance.groups.remove(staff_group)

        if self.cleaned_data.get('is_grade_user'):
            self.instance.groups.add(grade_user_group)
        else:
            self.instance.groups.remove(grade_user_group)


class UserMergeSelectionForm(forms.Form, BootstrapMixin):
    main_user = forms.ModelChoiceField(UserProfile.objects.all())
    other_user = forms.ModelChoiceField(UserProfile.objects.all())


class LotteryForm(forms.Form, BootstrapMixin):
    number_of_winners = forms.IntegerField(label=_("Number of Winners"), initial=3)


class EmailTemplateForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = EmailTemplate
        exclude = ("name", )


class FaqSectionForm(forms.ModelForm, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["title_de"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["title_en"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = FaqSection
        exclude = ()


class FaqQuestionForm(forms.ModelForm, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["question_de"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["question_en"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["answer_de"].widget.attrs['class'] = 'form-control'
        self.fields["answer_en"].widget.attrs['class'] = 'form-control'
        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = FaqQuestion
        exclude = ("section",)


class TextAnswerForm(forms.ModelForm, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['original_answer'].disabled = "True"

    class Meta:
        model = TextAnswer
        fields = ("original_answer", "reviewed_answer",)

    def clean_reviewed_answer(self):
        reviewed_answer = normalize_newlines(self.cleaned_data.get('reviewed_answer'))
        if reviewed_answer == normalize_newlines(self.instance.original_answer) or reviewed_answer == '':
            return None
        return reviewed_answer


class ExportSheetForm(forms.Form, BootstrapMixin):
    def __init__(self, semester, *args, **kwargs):
        super(ExportSheetForm, self).__init__(*args, **kwargs)
        course_types = CourseType.objects.filter(courses__semester=semester).distinct()
        course_type_tuples = [(ct.pk, ct.name) for ct in course_types]
        self.fields['selected_course_types'] = forms.MultipleChoiceField(
            choices=course_type_tuples,
            required=True,
            widget=forms.CheckboxSelectMultiple(),
            label=_("Course types")
        )
