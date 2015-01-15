from django import forms
from django.core.exceptions import ValidationError
from django.forms.fields import FileField
from django.forms.models import BaseInlineFormSet
from django.utils.translation import ugettext_lazy as _
from django.utils.text import normalize_newlines

from evap.evaluation.tools import STATES_ORDERED
from evap.evaluation.forms import BootstrapMixin, QuestionnaireMultipleChoiceField
from evap.evaluation.models import Contribution, Course, Question, Questionnaire, \
                                   Semester, UserProfile, FaqSection, FaqQuestion, \
                                   EmailTemplate, TextAnswer
from evap.staff.fields import ToolTipModelMultipleChoiceField
from evap.staff.tools import EMAIL_RECIPIENTS


class ImportForm(forms.Form, BootstrapMixin):
    vote_start_date = forms.DateField(label=_(u"First date to vote"), localize=True)
    vote_end_date = forms.DateField(label=_(u"Last date to vote"), localize=True)

    excel_file = forms.FileField(label=_(u"Excel file"))


class UserImportForm(forms.Form, BootstrapMixin):
    excel_file = forms.FileField(label=_(u"Excel file"))


class SemesterForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Semester
        fields = "__all__"


class CourseForm(forms.ModelForm, BootstrapMixin):
    general_questions = QuestionnaireMultipleChoiceField(Questionnaire.objects.filter(is_for_contributors=False, obsolete=False), label=_(u"General questions"))
    last_modified_time_2 = forms.DateTimeField(label=_(u"Last modified"), required=False, localize=True)
    last_modified_user_2 = forms.CharField(label=_(u"Last modified by"), required=False)

    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'kind', 'degree', 'is_graded',
                  'vote_start_date', 'vote_end_date', 'participants',
                  'general_questions',
                  'last_modified_time_2', 'last_modified_user_2')

    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)

        self.fields['vote_start_date'].localize = True
        self.fields['vote_end_date'].localize = True
        self.fields['kind'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('kind', flat=True).order_by().distinct()])
        self.fields['degree'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('degree', flat=True).order_by().distinct()])
        self.fields['participants'].queryset = UserProfile.objects.order_by("last_name", "first_name", "username")
        self.fields['participants'].help_text = ""

        if self.instance.general_contribution:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]

        self.fields['last_modified_time_2'].initial = self.instance.last_modified_time
        self.fields['last_modified_time_2'].widget.attrs['readonly'] = "True"
        if self.instance.last_modified_user:
            self.fields['last_modified_user_2'].initial = self.instance.last_modified_user.full_name
        self.fields['last_modified_user_2'].widget.attrs['readonly'] = "True"

        if self.instance.state == "inEvaluation":
            self.fields['vote_start_date'].widget.attrs['readonly'] = "True"
            self.fields['vote_end_date'].widget.attrs['readonly'] = "True"

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


class ContributionForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Contribution
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super(ContributionForm, self).__init__(*args, **kwargs)
        self.fields['contributor'].widget.attrs['class'] = 'form-control'

        self.fields['contributor'].queryset = UserProfile.objects.order_by('username')
        self.fields['questionnaires'] = QuestionnaireMultipleChoiceField(Questionnaire.objects.filter(is_for_contributors=True, obsolete=False), label=_("Questionnaires"))
        self.fields['order'].widget = forms.HiddenInput()

    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        exclude.remove('course') # allow checking against the missing attribute

        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)


class CourseEmailForm(forms.Form, BootstrapMixin):
    recipients = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple(), choices=EMAIL_RECIPIENTS, label=_("Send email to"))
    subject = forms.CharField(label=_("Subject"))
    body = forms.CharField(widget=forms.Textarea(), label=_("Message"))

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance')
        self.template = EmailTemplate()
        super(CourseEmailForm, self).__init__(*args, **kwargs)

    def clean(self):
        self.recipient_groups = self.cleaned_data.get('recipients')

        if not self.recipient_groups:
            raise forms.ValidationError(_(u"No recipient selected. Choose at least one group of recipients."))

        return self.cleaned_data

    # returns whether all recepients have an email address
    def all_recepients_reachable(self):
        return self.missing_email_addresses() == 0

    # returns the number of recepients without an email address
    def missing_email_addresses(self):
        recipients = self.template.recipient_list_for_course(self.instance, self.recipient_groups)
        return len([user for user in recipients if not user.email])

    def send(self):
        self.template.subject = self.cleaned_data.get('subject')
        self.template.body = self.cleaned_data.get('body')
        self.template.send_to_users_in_courses([self.instance], self.recipient_groups)


class QuestionnaireForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Questionnaire
        fields = "__all__"
        widgets = {
            'index': forms.HiddenInput(),
        }


class ReviewTextAnswerForm(forms.ModelForm, BootstrapMixin):
    reviewed_answer = forms.CharField(widget=forms.Textarea(), label=_("Answer"), required=False)
    needs_further_review = forms.BooleanField(label=_("Needs further review"), required=False)
    hidden = forms.BooleanField(label=_("Do not publish"), required=False)

    class Meta:
        fields = ('reviewed_answer', 'needs_further_review', 'hidden')
        model = TextAnswer

    def __init__(self, *args, **kwargs):
        super(ReviewTextAnswerForm, self).__init__(*args, **kwargs)
        # since setting the initial value on fields corresponding to a model field has no effect,
        # we'll set the initial value on the form, which works.
        self.initial['reviewed_answer'] = self.instance.answer

    def clean(self):
        reviewed_answer = self.cleaned_data.get("reviewed_answer") or ""
        needs_further_review = self.cleaned_data.get("needs_further_review")

        # if the answer was not edited, don't store the original answer again.
        if normalize_newlines(self.instance.original_answer) == normalize_newlines(reviewed_answer):
            self.cleaned_data["reviewed_answer"] = ""

        if not reviewed_answer.strip():
            self.cleaned_data["hidden"] = True
            
        self.instance.checked = not needs_further_review

        return self.cleaned_data


class AtLeastOneFormSet(BaseInlineFormSet):
    def clean(self):
        count = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                count += 1

        if count < 1:
            raise forms.ValidationError(_(u'You must have at least one of these.'))


class ContributionFormSet(AtLeastOneFormSet):
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
                form_with_errors.cleaned_data['id'] = deleted_form.cleaned_data['id']
                form_with_errors.instance = deleted_form.instance
                # we modified the form, so we have to force re-validation
                form_with_errors.full_clean()


    def clean(self):
        self.handle_deleted_and_added_contributions()

        super(ContributionFormSet, self).clean()

        found_contributor = set()
        count_responsible = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            contributor = form.cleaned_data.get('contributor')
            if contributor is None:
                raise forms.ValidationError(_(u'Please select the name of each added contributor. Remove empty rows if necessary.'))
            if contributor and contributor in found_contributor:
                raise forms.ValidationError(_(u'Duplicate contributor found. Each contributor should only be used once.'))
            elif contributor:
                found_contributor.add(contributor)

            if form.cleaned_data.get('responsible'):
                count_responsible += 1

        if count_responsible < 1:
            raise forms.ValidationError(_(u'No responsible contributor found. Each course must have exactly one responsible contributor.'))
        elif count_responsible > 1:
            raise forms.ValidationError(_(u'Too many responsible contributors found. Each course must have exactly one responsible contributor.'))


class IdLessQuestionFormSet(AtLeastOneFormSet):
    class PseudoQuerySet(list):
        db = None

    def __init__(self, data=None, files=None, instance=None, save_as_new=False, prefix=None, queryset=None):
        self.save_as_new = save_as_new
        self.instance = instance
        super(BaseInlineFormSet, self).__init__(data, files, prefix=prefix, queryset=queryset)

    def get_queryset(self):
        if not hasattr(self, '_queryset'):
            self._queryset = IdLessQuestionFormSet.PseudoQuerySet()
            self._queryset.extend([Question(text_de=e.text_de, text_en=e.text_en, kind=e.kind) for e in self.queryset.all()])
            self._queryset.db = self.queryset.db
        return self._queryset


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        self.fields['text_de'].widget = forms.TextInput(attrs={'class':'form-control'})
        self.fields['text_en'].widget = forms.TextInput(attrs={'class':'form-control'})
        self.fields['kind'].widget.attrs['class'] = 'form-control'


class QuestionnairesAssignForm(forms.Form, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        semester = kwargs.pop('semester')
        kinds = kwargs.pop('kinds')
        super(QuestionnairesAssignForm, self).__init__(*args, **kwargs)

        for kind in kinds:
            self.fields[kind] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False, is_for_contributors=False))
        self.fields['Responsible contributor'] = ToolTipModelMultipleChoiceField(label=_('Responsible contributor'), required=False, queryset=Questionnaire.objects.filter(obsolete=False, is_for_contributors=True))

    # overwritten because of https://code.djangoproject.com/ticket/12645
    # users can specify the field name (it's a course type), and include e.g. umlauts there
    # might be fixed in python 3
    def _clean_fields(self):
        for name, field in self.fields.items():
            # value_from_datadict() gets the data from the data dictionaries.
            # Each widget type knows how to retrieve its own data, because some
            # widgets split data over several HTML fields.
            value = field.widget.value_from_datadict(self.data, self.files, self.add_prefix(name))
            try:
                if isinstance(field, FileField):
                    initial = self.initial.get(name, field.initial)
                    value = field.clean(value, initial)
                else:
                    value = field.clean(value)
                self.cleaned_data[name] = value

                name2 = u'clean_%s' % name
                name2 = name2.encode('iso-8859-1')
                if hasattr(self, name2):
                    value = getattr(self, 'clean_%s' % name)()
                    self.cleaned_data[name] = value
            except ValidationError as e:
                self._errors[name] = self.error_class(e.messages)
                if name in self.cleaned_data:
                    del self.cleaned_data[name]


class SelectCourseForm(forms.Form, BootstrapMixin):
    def __init__(self, courses, *args, **kwargs):
        super(SelectCourseForm, self).__init__(*args, **kwargs)
        self.selected_courses = []

        for course in courses:
            label = '%s (%s) (%s)' % (course.name, course.kind, STATES_ORDERED[course.state])
            self.fields[str(course.id)] = forms.BooleanField(label=label, required=False)

    def clean(self):
        for course_id, selected in self.cleaned_data.items():
            if selected:
                self.selected_courses.append(Course.objects.get(pk=course_id))
        return self.cleaned_data


class UserForm(forms.ModelForm, BootstrapMixin):
    courses_participating_in = forms.IntegerField()

    class Meta:
        model = UserProfile
        fields = ('username', 'title', 'first_name', 'last_name', 'email', 'delegates', 'cc_users')

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)

        all_users = UserProfile.objects.order_by('username')
        # fix generated form
        self.fields['delegates'].required = False
        self.fields['delegates'].queryset = all_users
        self.fields['delegates'].help_text = ""
        self.fields['cc_users'].required = False
        self.fields['cc_users'].queryset = all_users
        self.fields['cc_users'].help_text = ""
        courses_of_current_semester = Course.objects.filter(semester=Semester.active_semester())
        self.fields['courses_participating_in'] = forms.ModelMultipleChoiceField(courses_of_current_semester,
                                                                          initial=courses_of_current_semester.filter(participants=self.instance) if self.instance.pk else (),
                                                                          label=_("Courses participating in (active semester)"),
                                                                          help_text="",
                                                                          required=False)
        self.fields['courses_participating_in'].help_text = ""

    def clean_username(self):
        conflicting_user = UserProfile.objects.filter(username__iexact=self.cleaned_data.get('username'))
        if not conflicting_user.exists():
            return self.cleaned_data.get('username')

        if self.instance and self.instance.pk:
            if conflicting_user[0] == self.instance:
                # there is a user with this name but that's me
                return self.cleaned_data.get('username')

        raise forms.ValidationError(_(u"A user with the username '%s' already exists") % self.cleaned_data.get('username'))

    def _post_clean(self, *args, **kw):
        if self._errors:
            return
        
        self.instance.username = self.cleaned_data.get('username').strip().lower()
        self.instance.title = self.cleaned_data.get('title').strip()
        self.instance.first_name = self.cleaned_data.get('first_name').strip()
        self.instance.last_name = self.cleaned_data.get('last_name').strip()
        self.instance.email = self.cleaned_data.get('email').strip().lower()
        
        # we need to do a save before course_set is set because the user needs to have an id there
        self.instance.save()
        self.instance.course_set = list(self.instance.course_set.exclude(semester=Semester.active_semester)) + list(self.cleaned_data.get('courses_participating_in'))

        super(UserForm, self)._post_clean(*args, **kw)


class LotteryForm(forms.Form, BootstrapMixin):
    number_of_winners = forms.IntegerField(label=_(u"Number of Winners"), initial=3)


class EmailTemplateForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = EmailTemplate
        exclude = ("name", )


class FaqSectionForm(forms.ModelForm, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        super(FaqSectionForm, self).__init__(*args, **kwargs)

        self.fields["title_de"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["title_en"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = FaqSection
        exclude = ()


class FaqQuestionForm(forms.ModelForm, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        super(FaqQuestionForm, self).__init__(*args, **kwargs)

        self.fields["question_de"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["question_en"].widget = forms.TextInput(attrs={'class': 'form-control'})
        self.fields["answer_de"].widget.attrs['class'] = 'form-control'
        self.fields["answer_en"].widget.attrs['class'] = 'form-control'
        self.fields["order"].widget = forms.HiddenInput()

    class Meta:
        model = FaqQuestion
        exclude = ("section",)

