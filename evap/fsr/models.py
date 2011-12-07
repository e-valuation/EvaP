from django.conf import settings
from django.core.mail import EmailMessage
from django.db import models
from django.shortcuts import get_object_or_404
from django.template import Context, Template
from django.utils.translation import ugettext_lazy as _


class EmailTemplate(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    
    use = models.BooleanField(verbose_name=_("Use this template"), default=True)
    
    subject = models.CharField(max_length=100, verbose_name=_(u"Subject"))
    body = models.TextField(verbose_name=_("Body"))
    
    @classmethod
    def create_initial_instances(cls):
        cls(pk=0, name="Template for lecturer review", subject="[EvaP] New Course ready for approval", body="").save()
        cls(pk=1, name="Template for student reminder", subject="[EvaP] Only 2 weeks left to evaluate", body="").save()
        cls(pk=2, name="Template for publishing", subject="[EvaP] A course has been published", body="").save()
    
    @classmethod
    def get_review_template(cls):
        return get_object_or_404(cls, pk=0)
    
    @classmethod
    def get_reminder_template(cls):
        return get_object_or_404(cls, pk=1)
    
    @classmethod
    def get_publish_template(cls):
        return get_object_or_404(cls, pk=2)
        
    @classmethod
    def get_logon_key_template(cls):
        return get_object_or_404(cls, pk=3)
       
    def receipient_list_for_course(self, course, send_to_lecturers, send_to_participants):
        if send_to_participants:
            for user in course.participants.all():
                yield user
        
        if send_to_lecturers:
            for assignment in course.assignments.exclude(lecturer=None):
                if assignment.lecturer.get_profile().is_lecturer:
                    yield assignment.lecturer
    
    def render_string(self, text, dictionary):
        template = Template(text)
        return template.render(Context(dictionary))
    
    def send_courses(self, courses, send_to_lecturers, send_to_participants):
        # pivot course-user relationship
        user_course_map = {}
        for course in courses:
            for user in [user for user in self.receipient_list_for_course(course, send_to_lecturers, send_to_participants) if user.email != ""]:
                if user in user_course_map:
                    user_course_map[user].append(course)
                else:
                    user_course_map[user] = [course]
        
        # send emails on a per user basis
        for user, courses in user_course_map.iteritems():
            # if user is lecturer, also send to proxies
            cc = [p.email for p in user.get_profile().proxies.all() if p.email] if user.get_profile().is_lecturer else []
            
            mail = EmailMessage(
                subject = self.render_string(self.subject, {'user': user, 'courses': courses}),
                body = self.render_string(self.body, {'user': user, 'courses': courses}),
                to = [user.email],
                cc = cc,
                bcc = [a[1] for a in settings.MANAGERS],
                headers = {'Reply-To': settings.REPLY_TO_EMAIL})
            mail.send(False)
    
    def send_user(self, user):
        if not user.email:
            return
        
        mail = EmailMessage(
            subject = self.render_string(self.subject, {'user': user}),
            body = self.render_string(self.body, {'user': user}),
            to = [user.email],
            bcc = [a[1] for a in settings.MANAGERS],
            headers = {'Reply-To': settings.REPLY_TO_EMAIL})
        mail.send(False)
