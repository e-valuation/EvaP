import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import ugettext as _
from django.core.urlresolvers import resolve, Resolver404
from django.views.decorators.http import require_POST

from evap.evaluation.forms import NewKeyForm, LoginUsernameForm
from evap.evaluation.models import UserProfile, FaqSection, EmailTemplate, Semester

logger = logging.getLogger(__name__)


def index(request):
    """Main entry page into EvaP providing all the login options available. The username/password
       login is thought to be used for internal users, e.g. by connecting to a LDAP directory.
       The login key mechanism is meant to be used to include external participants, e.g. visiting
       students or visiting contributors.
    """

    # parse the form data into the respective form
    submit_type = request.POST.get("submit_type", "no_submit")
    new_key_form = NewKeyForm(request.POST if submit_type == "new_key" else None)
    login_username_form = LoginUsernameForm(request, request.POST if submit_type == "login_username" else None)

    # process form data
    if request.method == 'POST':
        if new_key_form.is_valid():
            # user wants a new login key
            profile = new_key_form.get_user()
            profile.generate_login_key()
            profile.save()

            EmailTemplate.send_login_url_to_user(new_key_form.get_user())

            messages.success(request, _("We sent you an email with a one-time login URL. Please check your inbox."))
            return redirect('evaluation:index')
        elif login_username_form.is_valid():
            # user would like to login with username and password and passed password test
            auth_login(request, login_username_form.get_user())

            # clean up our test cookie
            if request.session.test_cookie_worked():
                request.session.delete_test_cookie()

    # if not logged in by now, render form
    if not request.user.is_authenticated():
        # set test cookie to verify whether they work in the next step
        request.session.set_test_cookie()

        template_data = dict(new_key_form=new_key_form, login_username_form=login_username_form)
        return render(request, "index.html", template_data)
    else:
        user, __ = UserProfile.objects.get_or_create(username=request.user.username)

        # check for redirect variable
        redirect_to = request.GET.get("next", None)
        if redirect_to is not None:
            if redirect_to.startswith("/staff/"):
                if request.user.is_staff:
                    return redirect(redirect_to)
            elif redirect_to.startswith("/grades/"):
                if request.user.is_grade_publisher:
                    return redirect(redirect_to)
            elif redirect_to.startswith("/contributor/"):
                if user.is_contributor:
                    return redirect(redirect_to)
            elif redirect_to.startswith("/student/"):
                if user.is_participant:
                    return redirect(redirect_to)
            else:
                try:
                    resolve(redirect_to)
                except Resolver404:
                    pass
                else:
                    return redirect(redirect_to)

        # redirect user to appropriate start page
        if request.user.is_staff:
            return redirect('staff:index')
        elif request.user.is_grade_publisher:
            return redirect('grades:semester_view', Semester.active_semester().id)
        elif user.is_student:
            return redirect('student:index')
        elif user.is_contributor_or_delegate:
            return redirect('contributor:index')
        elif user.is_participant:
            return redirect('student:index')
        else:
            return redirect('results:index')


def faq(request):
    return render(request, "faq.html", dict(sections=FaqSection.objects.all()))


def legal_notice(request):
    return render(request, "legal_notice.html", dict())


@require_POST
@login_required
def feedback_send(request):
    sender_email = request.user.email
    message = request.POST.get("message")
    subject = "Feedback from {}".format(sender_email)

    if message:
        mail = EmailMessage(
            subject=subject,
            body=message,
            to=[settings.FEEDBACK_EMAIL])

        try:
            mail.send()
            logger.info('Sent feedback email: \n{}\n'.format(mail.message()))
        except Exception:
            logger.exception('An exception occurred when sending the following feedback email:\n{}\n'.format(mail.message()))

    return HttpResponse()
