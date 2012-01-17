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

from evap.evaluation.forms import BootstrapMixin
from evap.evaluation.models import Assignment, Course, Question, Questionnaire, \
                                   Semester, TextAnswer, UserProfile
from evap.fsr.models import EmailTemplate
from evap.fsr.fields import UserModelMultipleChoiceField, ToolTipModelMultipleChoiceField


class ImportForm(forms.Form, BootstrapMixin):
    vote_start_date = forms.DateField(label=_(u"first date to vote"))
    vote_end_date = forms.DateField(label=_(u"last date to vote"))
    
    excel_file = forms.FileField(label=_(u"excel file"))
    
    def __init__(self, *args, **kwargs):
        super(ImportForm, self).__init__(*args, **kwargs)
        
        self.fields['vote_start_date'].localize = True
        self.fields['vote_start_date'].widget = forms.DateInput()
        
        self.fields['vote_end_date'].localize = True
        self.fields['vote_end_date'].widget = forms.DateInput()


class SemesterForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Semester


class CourseForm(forms.ModelForm, BootstrapMixin):
    general_questions = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False))
    
    class Meta:
        model = Course
        fields = ('name_de', 'name_en', 'kind', 'study',
                  'vote_start_date', 'vote_end_date', 'participants',
                  'general_questions')
    
    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)
        self.fields['participants'] = UserModelMultipleChoiceField(queryset=User.objects.order_by("last_name", "username"))
        
        if self.instance.general_assignment:
            self.fields['general_questions'].initial = [q.pk for q in self.instance.general_assignment.questionnaires.all()]
        
        self.fields['vote_start_date'].localize = True
        self.fields['vote_start_date'].widget = forms.DateInput()
        if self.instance.state == "inEvaluation":
            self.fields['vote_start_date'].required = False
            self.fields['vote_start_date'].widget.attrs['disabled'] = True
        
        self.fields['vote_end_date'].localize = True
        self.fields['vote_end_date'].widget = forms.DateInput()
        
        self.fields['kind'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('kind', flat=True).order_by().distinct()])
        self.fields['study'].widget = forms.Select(choices=[(a, a) for a in Course.objects.values_list('study', flat=True).order_by().distinct()])
    
    def save(self, *args, **kw):
        super(CourseForm, self).save(*args, **kw)
        self.instance.general_assignment.questionnaires = self.cleaned_data.get('general_questions')
        self.instance.save()


class AssignmentForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Assignment
    
    def __init__(self, *args, **kwargs):
        super(AssignmentForm, self).__init__(*args, **kwargs)
        self.fields['lecturer'].queryset = User.objects.order_by("username")
    
    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        exclude.remove('course') # allow checking against the missing attribute
        
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError, e:
            self._update_errors(e.message_dict)



class CourseEmailForm(forms.Form, BootstrapMixin):
    sendToParticipants = forms.BooleanField(label=_("Send to participants?"), required=False, initial=True)
    sendToLecturers = forms.BooleanField(label=_("Send to lecturers?"), required=False)
    subject = forms.CharField(label=_("Subject"))
    body = forms.CharField(widget=forms.Textarea(), label=_("Body"))
    
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance')
        self.template = EmailTemplate()
        super(CourseEmailForm, self).__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = self.cleaned_data
        
        if not (cleaned_data.get('sendToParticipants') or cleaned_data.get('sendToLecturers')):
            raise forms.ValidationError(_(u"No recipient selected. Choose at least participants or lecturers."))
        
        return cleaned_data

    # returns whether all recepients have an email address
    def all_recepients_reachable(self):
        return self.missing_email_addresses() == 0
    
    # returns the number of recepients without an email address
    def missing_email_addresses(self):
        return len(list(self.template.receipient_list_for_course(self.instance, self.cleaned_data.get('sendToLecturers'), self.cleaned_data.get('sendToParticipants'))))
    
    def send(self):
        self.template.subject = self.cleaned_data.get('subject')
        self.template.body = self.cleaned_data.get('body')
        self.template.send_courses([self.instance], self.cleaned_data.get('sendToLecturers'), self.cleaned_data.get('sendToParticipants'))

class QuestionnaireForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = Questionnaire


class CensorTextAnswerForm(forms.ModelForm, BootstrapMixin):
    edited_answer = forms.CharField(widget=forms.Textarea(), label=_("Answer"))
    needs_further_review = forms.BooleanField(label=_("Needs further review"), required=False)
    
    class Meta:
        fields = ('edited_answer', 'needs_further_review')
    
    def __init__(self, *args, **kwargs):
        super(CensorTextAnswerForm, self).__init__(*args, **kwargs)
        
        self.fields['edited_answer'].initial = self.instance.answer
    
    def clean(self):
        cleaned_data = self.cleaned_data
        edited_answer = cleaned_data.get("edited_answer")
        needs_further_review = cleaned_data.get("needs_further_review")
        
        if self.instance.original_answer == normalize_newlines(edited_answer):
            # simply approved
            self.instance.checked = True
        elif not edited_answer.strip():
            # hidden
            self.instance.hidden = True
        else:
            # censored
            self.instance.checked = True
            self.instance.censored_answer = edited_answer
        
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

class LecturerFormSet(AtLeastOneFormSet):
    def clean(self):
        super(LecturerFormSet, self).clean()
        
        found_lecturer = []
        for form in self.forms:
            try:
                if form.cleaned_data:
                    lecturer = form.cleaned_data.get('lecturer')
                    if lecturer and lecturer in found_lecturer:
                        raise forms.ValidationError(_(u'Duplicate lecturer found. Each lecturer should only be used once.'))
                    elif lecturer:
                        found_lecturer.append(lecturer)
            except AttributeError:
                # annoyingly, if a subform is invalid Django explicity raises
                # an AttributeError for cleaned_data
                pass

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
    
    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        self.fields['text_de'].widget = forms.TextInput()
        self.fields['text_en'].widget = forms.TextInput()


class QuestionnairesAssignForm(forms.Form, BootstrapMixin):
    def __init__(self, *args, **kwargs):
        semester = kwargs.pop('semester')
        extras = kwargs.pop('extras', ())
        super(QuestionnairesAssignForm, self).__init__(*args, **kwargs)
        
        # course kinds
        for kind in semester.course_set.filter(state__in=['prepared', 'lecturerApproved', 'new', 'approved']).values_list('kind', flat=True).order_by().distinct():
            self.fields[kind] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False))
        
        # extra kinds
        for extra in extras:
            self.fields[extra] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False))
    
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
    def __init__(self, queryset, *args, **kwargs):
        super(SelectCourseForm, self).__init__(*args, **kwargs)
        self.queryset = queryset
        self.selected_courses = []
        
        for course in self.queryset:
            self.fields[str(course.id)] = forms.BooleanField(label=course.name, required=False)
    
    def clean(self):
        cleaned_data = self.cleaned_data
        for id, selected in cleaned_data.iteritems():
            if selected:
                self.selected_courses.append(Course.objects.get(pk=id))
        return cleaned_data

    
class UserForm(forms.ModelForm, BootstrapMixin):
    username = forms.CharField()
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.CharField(required=False)
    fsr = forms.BooleanField(required=False, label=_("FSR Member"))
    proxies = UserModelMultipleChoiceField(queryset=User.objects.order_by("username"))
    
    class Meta:
        model = UserProfile
        exclude = ('user',)
        fields = ['username', 'title', 'first_name', 'last_name', 'email', 'picture', 'proxies', 'is_lecturer']
    
    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        
        # fix generated form
        self.fields['proxies'].required = False
        
        # load user fields
        self.fields['username'].initial = self.instance.user.username
        self.fields['first_name'].initial = self.instance.user.first_name
        self.fields['last_name'].initial = self.instance.user.last_name
        self.fields['email'].initial = self.instance.user.email
        self.fields['fsr'].initial = self.instance.user.is_staff

    def save(self, *args, **kw):
        # first save the user, so that the profile gets created for sure
        self.instance.user.username = self.cleaned_data.get('username')
        self.instance.user.first_name = self.cleaned_data.get('first_name')
        self.instance.user.last_name = self.cleaned_data.get('last_name')
        self.instance.user.email = self.cleaned_data.get('email')
        self.instance.user.is_staff = self.cleaned_data.get('fsr')
        self.instance.user.save()
        self.instance = self.instance.user.get_profile()
        
        super(UserForm, self).save(*args, **kw)


class LotteryForm(forms.Form, BootstrapMixin):
    number_of_winners = forms.IntegerField(label=_(u"Number of Winners"), initial=3)


class EmailTemplateForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = EmailTemplate
        exclude = ("name", )
