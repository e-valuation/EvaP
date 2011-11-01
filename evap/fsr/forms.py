from django import forms
from django.conf import settings
from django.core.mail import EmailMessage
from django.forms.models import BaseInlineFormSet, BaseModelFormSet
from django.utils.translation import ugettext_lazy as _

from evaluation.models import *
from student.forms import GRADE_CHOICES, coerce_grade
from fsr.fields import *


class ImportForm(forms.Form):
    vote_start_date = forms.DateField(label = _(u"first date to vote"))
    vote_end_date = forms.DateField(label = _(u"last date to vote"))
    
    excel_file = forms.FileField(label = _(u"excel file"))
    
    def __init__(self, *args, **kwargs):
        super(ImportForm, self).__init__(*args, **kwargs)
        
        self.fields['vote_start_date'].localize = True
        self.fields['vote_start_date'].widget = forms.DateInput()
        
        self.fields['vote_end_date'].localize = True
        self.fields['vote_end_date'].widget = forms.DateInput()


class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester


class CourseForm(forms.ModelForm):
    participants = UserModelMultipleChoiceField(queryset=User.objects.all())
    primary_lecturers = UserModelMultipleChoiceField(queryset=User.objects.all())
    secondary_lecturers = UserModelMultipleChoiceField(queryset=User.objects.all())
    
    class Meta:
        model = Course
        exclude = ("voters", "semester")
    
    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)
        self.fields['general_questions'] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False))
        self.fields['primary_lecturer_questions'] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False))
        self.fields['secondary_lecturer_questions'] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False))
        self.fields['secondary_lecturers'].required = False
        
        self.fields['vote_start_date'].localize = True
        self.fields['vote_start_date'].widget = forms.DateInput()
        
        self.fields['vote_end_date'].localize = True
        self.fields['vote_end_date'].widget = forms.DateInput()


class CourseEmailForm(forms.Form):
    sendToParticipants = forms.BooleanField(label = _("Send to participants?"), required=False, initial=True)
    sendToPrimaryLecturers = forms.BooleanField(label = _("Send to primary lecturers?"), required=False)
    sendToSecondaryLecturers = forms.BooleanField(label = _("Send to secondary lecturers?"), required=False)
    subject = forms.CharField(label = _("Subject"))
    body = forms.CharField(widget=forms.Textarea(), label = _("Body"))
    
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance')
        super(CourseEmailForm, self).__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = self.cleaned_data
        
        if not (cleaned_data.get('sendToParticipants') or cleaned_data.get('sendToPrimaryLecturers') or cleaned_data.get('sendToSecondaryLecturers')):
            raise forms.ValidationError(_(u"No recipient selected. Choose at least participants or lecturers."))
        
        return cleaned_data

    # returns whether all recepients have an email address    
    def all_recepients_reachable(self):
        return self.missing_email_addresses() == 0
    
    # returns the number of recepients without an email address
    def missing_email_addresses(self):
        return len([email for email in self.receipient_list if email == ""])
    
    @property
    def receipient_list(self):
        # cache result
        if hasattr(self, '_rcpts'):
            return self._rcpts
        
        self._rcpts = []
        for group, manager in {'sendToPrimaryLecturers': self.instance.primary_lecturers, 'sendToSecondaryLecturers': self.instance.secondary_lecturers}.iteritems():
            if self.cleaned_data.get(group):
                self._rcpts.extend([user.email for user in manager.all()])
        
        return self._rcpts
    
    def send(self):
        mail = EmailMessage(subject = self.cleaned_data.get('subject'),
                            body = self.cleaned_data.get('body'),
                            to = [email for email in self.receipient_list if email != ""],
                            bcc = [a[1] for a in settings.MANAGERS],
                            headers = {'Reply-To': settings.REPLY_TO_EMAIL})
        mail.send(False)


class QuestionnaireForm(forms.ModelForm):
    class Meta:
        model = Questionnaire


class CensorTextAnswerForm(forms.ModelForm):
    ACTION_CHOICES = (
        (u"1", _(u"Approved")),
        (u"2", _(u"Censored")),
        (u"3", _(u"Hide")),
        (u"4", _(u"Needs further review")),
    )

    class Meta:
        model = TextAnswer
        fields = ('censored_answer',)
    
    def __init__(self, *args, **kwargs):
        super(CensorTextAnswerForm, self).__init__(*args, **kwargs)
        self.fields['action'] = forms.TypedChoiceField(widget=forms.RadioSelect(), choices=self.ACTION_CHOICES, coerce=int)
    
    def clean(self):
        cleaned_data = self.cleaned_data
        action = cleaned_data.get("action")
        censored_answer = cleaned_data.get("censored_answer")
        
        if action == 2 and not censored_answer:
            raise forms.ValidationError(_(u'Censored answer missing.'))
        
        return cleaned_data


class QuestionFormSet(BaseInlineFormSet):
    def is_valid(self):
        return super(QuestionFormSet, self).is_valid() and not any([bool(e) for e in self.errors])  
    
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


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
    
    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        self.fields['text_de'].widget=forms.TextInput()
        self.fields['text_en'].widget=forms.TextInput()


class QuestionnairePreviewForm(forms.Form):
    """Dynamic form class that adds one field per question. Pass an iterable
    of questionnaires as `questionnaires` argument to the initializer.
    
    See http://jacobian.org/writing/dynamic-form-generation/"""
    
    def __init__(self, *args, **kwargs):
        questionnaire = kwargs.pop('questionnaire')
        super(QuestionnairePreviewForm, self).__init__(*args, **kwargs)
        
        # iterate over all questions in the questionnaire
        for question in questionnaire.question_set.all():
            # generic arguments for all kinds of fields
            field_args = dict(label=question.text)
            
            if question.is_text_question():
                field = forms.CharField(widget=forms.Textarea(), required=False, **field_args)
            elif question.is_grade_question():
                field = forms.TypedChoiceField(widget=forms.RadioSelect(), choices=GRADE_CHOICES, coerce=coerce_grade, **field_args)
            
            # create a field for the question, using the ids of both the
            # questionnaire and the question
            self.fields['question_%d' % (question.id)] = field


class QuestionnairesAssignForm(forms.Form):
    def __init__(self, *args, **kwargs):
        semester = kwargs.pop('semester')
        extras = kwargs.pop('extras', ())
        super(QuestionnairesAssignForm, self).__init__(*args, **kwargs)
        
        # course kinds
        for kind in semester.course_set.values_list('kind', flat=True).order_by().distinct():
            self.fields[kind] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False))
        
        # extra kinds
        for extra in extras:
            self.fields[extra] = ToolTipModelMultipleChoiceField(required=False, queryset=Questionnaire.objects.filter(obsolete=False))


class SelectCourseForm(forms.Form):
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

    
class UserForm(forms.ModelForm):
    username = forms.CharField()
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.CharField(required=False)
    
    proxies = UserModelMultipleChoiceField(queryset=User.objects.all())
    
    class Meta:
        model = UserProfile
        exclude = ('user',)
        fields = ['username', 'title', 'first_name', 'last_name', 'email', 'picture', 'fsr', 'proxies']
    
    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        
        # fix generated form
        self.fields['proxies'].required=False
        
        # load user fields
        self.fields['username'].initial = self.instance.user.username
        self.fields['first_name'].initial = self.instance.user.first_name
        self.fields['last_name'].initial = self.instance.user.last_name
        self.fields['email'].initial = self.instance.user.email

    def save(self, *args, **kw):
        # first save the user, so that the profile gets created for sure
        self.instance.user.username     = self.cleaned_data.get('username')
        self.instance.user.first_name   = self.cleaned_data.get('first_name')
        self.instance.user.last_name    = self.cleaned_data.get('last_name')
        self.instance.user.email        = self.cleaned_data.get('email')
        self.instance.user.save()
        self.instance = self.instance.user.get_profile()
        
        super(UserForm, self).save(*args, **kw)


class LotteryForm(forms.Form):
    number_of_winners = forms.IntegerField(label=_(u"Number of Winners"), initial=3)

class EmailTemplateForm(forms.ModelForm):    
    class Meta:
        model = EmailTemplate
        exclude = ("name", )