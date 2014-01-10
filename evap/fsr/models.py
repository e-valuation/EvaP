from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import models
from django.template import Context, Template, TemplateSyntaxError, TemplateEncodingError
from django.utils.translation import ugettext_lazy as _


def validate_template(value):
    """Field validator which ensures that the value can be compiled into a
    Django Template."""
    try:
        Template(value)
    except (TemplateSyntaxError, TemplateEncodingError) as e:
        raise ValidationError(str(e))


class EmailTemplate(models.Model):    
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Name"))
    
    subject = models.CharField(max_length=100, verbose_name=_(u"Subject"), validators=[validate_template])
    body = models.TextField(verbose_name=_("Body"), validators=[validate_template])
    
    @classmethod
    def get_review_template(cls):
        return cls.objects.get(name="Lecturer Review Notice")
    
    @classmethod
    def get_reminder_template(cls):
        return cls.objects.get(name="Student Reminder")
    
    @classmethod
    def get_publish_template(cls):
        return cls.objects.get(name="Publishing Notice")
        
    @classmethod
    def get_login_key_template(cls):
        return cls.objects.get(name="Login Key Created")
    
    @classmethod
    def recipient_list_for_course(cls, course, send_to_editors, send_to_contributors, send_to_participants):
        from evap.evaluation.models import UserProfile

        if send_to_participants:
            for user in course.participants.all():
                yield user
        
        if send_to_contributors:
            for contribution in course.contributions.exclude(contributor=None):
                yield contribution.contributor
        elif send_to_editors:
            for contribution in course.contributions.exclude(contributor=None).filter(can_edit=True):
                yield contribution.contributor
    
    @classmethod
    def render_string(cls, text, dictionary):
        return Template(text).render(Context(dictionary))
    
    def send_courses(self, courses, send_to_editors, send_to_contributors, send_to_participants, only_non_evaluated=False):
        from evap.evaluation.models import UserProfile

        # pivot course-user relationship
        user_course_map = {}
        for course in courses:
            for user in [user for user in self.recipient_list_for_course(course, send_to_editors, send_to_contributors, send_to_participants) if user.email != ""]:
                if (not only_non_evaluated) or (user not in course.voters.all()):
                    if user in user_course_map:
                        user_course_map[user].append(course)
                    else:
                        user_course_map[user] = [course]
        
        # send emails on a per user basis
        for user, courses in user_course_map.iteritems():
            
            cc = []
            # if email will be sent to editors, also send to all their delegates in CC
            if send_to_editors:
                for course in courses:
                    if course.contributions.filter(can_edit=True, contributor=user).exists():
                        cc = [p.email for p in UserProfile.get_for_user(user).delegates.all() if p.email]
                        break
            
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
