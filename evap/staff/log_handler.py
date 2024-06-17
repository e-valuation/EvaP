from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.log import AdminEmailHandler


def mail_managers(subject, message, fail_silently=False, connection=None, html_message=None):
    """Send a message to the managers, as defined by the MANAGERS setting."""
    from evap.evaluation.models import UserProfile

    managers = UserProfile.objects.filter(groups__name="Manager", email__isnull=False)
    if not managers:
        return
    mail = EmailMultiAlternatives(
        f"{settings.EMAIL_SUBJECT_PREFIX}{subject}",
        message,
        settings.SERVER_EMAIL,
        [manager.email for manager in managers],
        connection=connection,
    )
    if html_message:
        mail.attach_alternative(html_message, "text/html")
    mail.send(fail_silently=fail_silently)


class ManagerEmailHandler(AdminEmailHandler):
    def send_mail(self, subject, message, *args, **kwargs):
        mail_managers(subject, message, *args, connection=self.connection(), **kwargs)
