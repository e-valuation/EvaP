from django import forms
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.forms.fields import Field, FileField
from django.forms.models import BaseInlineFormSet
from django.template import Context, Template
from django.utils.translation import ugettext_lazy as _
from django.utils.text import normalize_newlines

from evap.evaluation.forms import BootstrapMixin, QuestionnaireMultipleChoiceField
from evap.evaluation.models import Contribution, Course, Question, Questionnaire, \
                                   Semester, TextAnswer, UserProfile
from evap.fsr.models import EmailTemplate
from evap.fsr.fields import UserModelMultipleChoiceField, ToolTipModelMultipleChoiceField


class ImportForm(forms.Form, BootstrapMixin):
    vote_start_date = forms.DateField(label=_(u"First date to vote"), localize=True)
    vote_end_date = forms.DateField(label=_(u"Last date to vote"), localize=True)
    
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
        fields = ('name_de', 'name_en', 'kind', 'degree',
                  'vote_start_date', 'vote_end_date', 'participants',
                  'general_questions',
                  'last_modified_time_2', 'last_modified_user_2')
    
    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)
        
        self.fields['vote_start_date'].localize = True
        self.fields['vote_end_date'].localize = True
        self.fields['kind'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('kind', flat=True).order_by().distinct()])
        self.fields['degree'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('degree', flat=True).order_by().distinct()])
        self.fields['participants'].queryset = User.objects.order_by("last_name", "first_name", "username")
        self.fields['participants'].help_text = ""
        
        if self.instance.general_contribution:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_contribution.questionnaires.all()]
        
        self.fields['last_modified_time_2'].initial = self.instance.last_modified_time
        self.fields['last_modified_time_2'].widget.attrs['readonly'] = True
        if self.instance.last_modified_user:
            self.fields['last_modified_user_2'].initial = UserProfile.get_for_user(self.instance.last_modified_user).full_name
        self.fields['last_modified_user_2'].widget.attrs['readonly'] = True

        if self.instance.state == "inEvaluation":
            self.fields['vote_start_date'].widget.attrs['readonly'] = True
            self.fields['vote_end_date'].widget.attrs['readonly'] = True
    
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
        
        self.fields['contributor'].queryset = User.objects.extra(select={'lower_username': 'lower(username)'}).order_by('lower_username')
        self.fields['questionnaires'] = QuestionnaireMultipleChoiceField(Questionnaire.objects.filter(is_for_contributors=True, obsolete=False), label=_("Questionnaires"))

    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        exclude.remove('course') # allow checking against the missing attribute
        
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e :
            self._update_errors(e)


class CourseEmailForm(forms.Form, BootstrapMixin):
    sendToParticipants = forms.BooleanField(label=_("Send to participants?"), required=False, initial=True)
    sendToEditors = forms.BooleanField(label=_("Send to editors?"), required=False)
    sendToContributors = forms.BooleanField(label=_("Send to all contributors (includes editors)?"), required=False)
    subject = forms.CharField(label=_("Subject"))
    body = forms.CharField(widget=forms.Textarea(), label=_("Body"))
    
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance')
        self.template = EmailTemplate()
        super(CourseEmailForm, self).__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = self.cleaned_data
        
        if not (cleaned_data.get('sendToParticipants') or cleaned_data.get('sendToEditors') or cleaned_data.get('sendToContributors')):
            raise forms.ValidationError(_(u"No recipient selected. Choose at least one group of recipients."))
        
        return cleaned_data

    # returns whether all recepients have an email address
    def all_recepients_reachable(self):
        return self.missing_email_addresses() == 0
    
    # returns the number of recepients without an email address
    def missing_email_addresses(self):
        return len([user for user in self.template.recipient_list_for_course(self.instance, self.cleaned_data.get('sendToEditors'), self.cleaned_data.get('sendToContributors'), self.cleaned_data.get('sendToParticipants')) if not user.email])
    
    def send(self):
        self.template.subject = self.cleaned_data.get('subject')
        self.template.body = self.cleaned_data.get('body')
        self.template.send_courses([self.instance], self.cleaned_data.get('sendToEditors'), self.cleaned_data.get('sendToContributors'), self.cleaned_data.get('sendToParticipants'))

class QuestionnaireForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Questionnaire
        fields = "__all__"


class ReviewTextAnswerForm(forms.ModelForm, BootstrapMixin):
    edited_answer = forms.CharField(widget=forms.Textarea(), label=_("Answer"), required=False)
    needs_further_review = forms.BooleanField(label=_("Needs further review"), required=False)
    hidden = forms.BooleanField(label=_("Hidden"), required=False)
    
    class Meta:
        fields = ('edited_answer', 'needs_further_review')
    
    def __init__(self, *args, **kwargs):
        super(ReviewTextAnswerForm, self).__init__(*args, **kwargs)
        
        self.fields['edited_answer'].initial = self.instance.answer
    
    def clean(self):
        cleaned_data = self.cleaned_data
        edited_answer = cleaned_data.get("edited_answer") or ""
        needs_further_review = cleaned_data.get("needs_further_review")
        hidden = cleaned_data.get("hidden")
        
        if not edited_answer.strip() or hidden:
            # hidden
            self.instance.checked = True
            self.instance.hidden = True        
        elif normalize_newlines(self.instance.original_answer) == normalize_newlines(edited_answer):
            # simply approved
            self.instance.checked = True
        else:
            # reviewed
            self.instance.checked = True
            self.instance.reviewed_answer = edited_answer
        
        if needs_further_review:
            self.instance.checked = False
            self.instance.hidden = False
        else:
            self.checked = True
        
        return cleaned_data


class AtLeastOneFormSet(BaseInlineFormSet):
    def is_valid(self):
        return super(AtLeastOneFormSet, self).is_valid() and not any([bool(e) for e in self.errors])
    
    def clean(self):
        # get forms that actually have valid data
        count = 0
        for form in self.forms:
            try:
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                    count += 1
            except AttributeError:
                # annoyingly, if a subform is invalid Django explicity raises
                # an AttributeError for cleaned_data
                pass
        
        if count < 1:
            raise forms.ValidationError(_(u'You must have at least one of these.'))


class ContributorFormSet(AtLeastOneFormSet):
    def clean(self):
        super(ContributorFormSet, self).clean()
        
        found_contributor = []
        count_responsible = 0
        for form in self.forms:
            try:
                if form.cleaned_data:
                    contributor = form.cleaned_data.get('contributor')
                    delete = form.cleaned_data.get('DELETE')
                    if contributor == None and not delete:
                        raise forms.ValidationError(_(u'Please select the name of each added contributor. Remove empty rows if necessary.'))
                    if contributor and contributor in found_contributor:
                        raise forms.ValidationError(_(u'Duplicate contributor found. Each contributor should only be used once.'))
                    elif contributor:
                        found_contributor.append(contributor)

                    if form.cleaned_data.get('responsible'):
                        count_responsible += 1
            
            except AttributeError:
                # annoyingly, if a subform is invalid Django explicity raises
                # an AttributeError for cleaned_data
                pass

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
        extras = kwargs.pop('extras', ())
        super(QuestionnairesAssignForm, self).__init__(*args, **kwargs)
        
        # course kinds
        for kind in semester.course_set.filter(state__in=['prepared', 'lecturerApproved', 'new', 'approved']).values_list('kind', flat=True).order_by().distinct():
            self.fields[kind] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False, is_for_contributors=False))
        
        # extra kinds
        for extra in extras:
            self.fields[extra] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False, is_for_contributors=False))
    
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
            except ValidationError, e:
                self._errors[name] = self.error_class(e.messages)
                if name in self.cleaned_data:
                    del self.cleaned_data[name]


class SelectCourseForm(forms.Form, BootstrapMixin):
    def __init__(self, degree, queryset, filter_func, *args, **kwargs):
        super(SelectCourseForm, self).__init__(*args, **kwargs)
        self.degree = degree
        self.queryset = queryset
        self.selected_courses = []
        self.filter_func = filter_func or (lambda x: True)
        
        for course in self.queryset:
            if self.filter_func(course):
                label = course.name + " (" + course.state + ")"
                self.fields[str(course.id)] = forms.BooleanField(label=label, required=False)
    
    def clean(self):
        cleaned_data = self.cleaned_data
        for id, selected in cleaned_data.iteritems():
            if selected:
                self.selected_courses.append(Course.objects.get(pk=id))
        return cleaned_data


class UserForm(forms.ModelForm, BootstrapMixin):
    represented_users = forms.IntegerField()
    
    # steal form field definitions for the User model
    locals().update(forms.fields_for_model(User, fields=('username', 'first_name', 'last_name', 'email', 'is_staff', 'is_superuser')))
    
    class Meta:
        model = UserProfile
        fields = ('username', 'title', 'first_name', 'last_name', 'email', 'picture', 'delegates', 'represented_users', 'is_staff', 'is_superuser')
    
    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        
        # fix generated form
        self.fields['delegates'].required = False
        self.fields['delegates'].queryset = User.objects.extra(select={'lower_username': 'lower(username)'}).order_by('lower_username')
        self.fields['delegates'].help_text = ""
        self.fields['is_staff'].label = _(u"FSR Member")
        self.fields['is_superuser'].label = _(u"EvaP Administrator")
        self.fields['represented_users'] = forms.ModelMultipleChoiceField(UserProfile.objects.all(),
                                                                      initial=self.instance.user.represented_users.all() if self.instance.pk else (),
                                                                      label=_("Represented Users"),
                                                                      help_text="",
                                                                      required=False)
        self.fields['represented_users'].help_text = ""
        
        # load user fields
        self.fields['username'].initial = self.instance.user.username
        self.fields['first_name'].initial = self.instance.user.first_name
        self.fields['last_name'].initial = self.instance.user.last_name
        self.fields['email'].initial = self.instance.user.email
        self.fields['is_staff'].initial = self.instance.user.is_staff
        self.fields['is_superuser'].initial = self.instance.user.is_superuser

    def clean_username(self):
        conflicting_user = User.objects.filter(username__iexact=self.cleaned_data.get('username'))
        if not conflicting_user.exists():
            return self.cleaned_data.get('username')
        
        if self.instance.user and self.instance.user.pk:
            if conflicting_user[0] == self.instance.user:
                # there is a user with this name but that's me
                return self.cleaned_data.get('username')
        
        raise forms.ValidationError(_(u"A user with the username '%s' already exists") % self.cleaned_data.get('username'))
    
    def _post_clean(self, *args, **kw):
        # first save the user, so that the profile gets created for sure
        self.instance.user.username = self.cleaned_data.get('username')
        self.instance.user.first_name = self.cleaned_data.get('first_name')
        self.instance.user.last_name = self.cleaned_data.get('last_name')
        self.instance.user.email = self.cleaned_data.get('email')
        self.instance.user.is_staff = self.cleaned_data.get('is_staff')
        self.instance.user.is_superuser = self.cleaned_data.get('is_superuser')
        self.instance.user.save()
        self.instance.user.represented_users = self.cleaned_data.get('represented_users')
        self.instance = UserProfile.get_for_user(self.instance.user)
        
        super(UserForm, self)._post_clean(*args, **kw)


class LotteryForm(forms.Form, BootstrapMixin):
    number_of_winners = forms.IntegerField(label=_(u"Number of Winners"), initial=3)


class EmailTemplateForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = EmailTemplate
        exclude = ("name", )
