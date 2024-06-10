import logging
from datetime import date, timedelta

from django.conf import settings
from django.contrib import auth, messages
from django.core.exceptions import SuspiciousOperation
from django.core.mail import EmailMessage
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import iri_to_uri
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.utils.translation import gettext as _
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django.views.i18n import set_language

from evap.evaluation.forms import LoginEmailForm, NewKeyForm, NotebookForm, ProfileForm
from evap.evaluation.models import EmailTemplate, FaqSection, Semester, UserProfile
from evap.evaluation.tools import HttpResponseNoContent, openid_login_is_active, password_login_is_active
from evap.middleware import no_login_required

logger = logging.getLogger(__name__)


def redirect_user_to_start_page(user):  # noqa: PLR0911
    active_semester = Semester.active_semester()

    if user.is_reviewer:
        if active_semester is not None:
            return redirect("staff:semester_view", active_semester.id)
        return redirect("staff:index")

    if user.startpage == UserProfile.StartPage.STUDENT and user.is_participant:
        return redirect("student:index")
    if user.startpage == UserProfile.StartPage.CONTRIBUTOR and user.is_responsible_or_contributor_or_delegate:
        return redirect("contributor:index")
    if user.startpage == UserProfile.StartPage.GRADES and user.is_grade_publisher and active_semester is not None:
        return redirect("grades:semester_view", active_semester.id)

    if user.is_grade_publisher:
        if active_semester is not None:
            return redirect("grades:semester_view", active_semester.id)
        return redirect("grades:index")
    if user.is_student:
        return redirect("student:index")
    if user.is_responsible_or_contributor_or_delegate:
        return redirect("contributor:index")

    return redirect("results:index")


@no_login_required
@sensitive_post_parameters("password")
def index(request):
    """Main entry page into EvaP providing all the login options available. The OpenID login is thought to be used for
    internal users. The login key mechanism is meant to be used to include external participants, e.g. visiting
    students or visiting contributors. A login with email and password is available if OpenID is deactivated.
    """

    # parse the form data into the respective form
    submit_type = request.POST.get("submit_type", "no_submit")
    new_key_form = NewKeyForm(request.POST if submit_type == "new_key" else None)

    if submit_type == "login_email" and not password_login_is_active():
        raise SuspiciousOperation

    login_email_form = LoginEmailForm(request, request.POST if submit_type == "login_email" else None)

    # process form data
    if request.method == "POST":
        if new_key_form.is_valid():
            # user wants a new login key
            profile = new_key_form.get_user()
            profile.ensure_valid_login_key()
            profile.save()

            EmailTemplate.send_login_url_to_user(new_key_form.get_user())

            messages.success(request, _("We sent you an email with a one-time login URL. Please check your inbox."))
            return redirect("evaluation:index")

        if login_email_form.is_valid():
            assert password_login_is_active()
            # user would like to login with email and password and passed password test
            auth.login(request, login_email_form.get_user())

            # clean up our test cookie
            if request.session.test_cookie_worked():
                request.session.delete_test_cookie()

            # redirect to this view again so the staff mode middleware runs for the authenticated user.
            redirect_to = request.GET.get("next", None)
            query_string = urlencode({"next": redirect_to}) if redirect_to else ""
            return redirect(reverse("evaluation:index") + "?" + query_string)

    # if not logged in by now, render form
    if not request.user.is_authenticated:
        # set test cookie to verify whether they work in the next step
        request.session.set_test_cookie()

        template_data = {
            "new_key_form": new_key_form,
            "login_email_form": login_email_form,
            "openid_active": openid_login_is_active(),
        }
        return render(request, "index.html", template_data)

    # check for redirect variable
    redirect_to = request.GET.get("next", None)
    if redirect_to is not None and url_has_allowed_host_and_scheme(redirect_to, None):
        # django asked us to use iri_to_uri: https://docs.djangoproject.com/en/3.0/releases/3.0/#id3
        return redirect(iri_to_uri(redirect_to))

    return redirect_user_to_start_page(request.user)


@no_login_required
def login_key_authentication(request, key):
    user = auth.authenticate(request, key=key)

    if user and not user.is_active:
        messages.error(request, _("Inactive users are not allowed to login."))
        return redirect("evaluation:index")

    # If we already have an authenticated user don't try to login a new user. Show an error message if another user
    # tries to login with a URL in this situation.
    if request.user.is_authenticated:
        if user != request.user:
            messages.error(
                request, _("Another user is currently logged in. Please logout first and then use the login URL again.")
            )
        return redirect("evaluation:index")

    if user and user.login_key_valid_until >= date.today():
        if request.method != "POST":
            template_data = {"username": user.full_name}
            return render(request, "external_user_confirm_login.html", template_data)

        # User is valid. Set request.user and persist user in the session by logging the user in.
        request.user = user
        auth.login(request, user)
        messages.success(request, _("Logged in as %s.") % user.full_name)
        # Invalidate the login key, but keep it stored so we can later identify the user that is trying to login and send a new link
        user.login_key_valid_until = date.today() - timedelta(1)
        user.save()
    elif user:
        # A user exists, but the login key is not valid anymore. Send the user a new one.
        user.ensure_valid_login_key()
        EmailTemplate.send_login_url_to_user(user)
        messages.warning(request, _("The login URL is not valid anymore. We sent you a new one to your email address."))
    else:
        messages.warning(request, _("Invalid login URL. Please request a new one below."))

    return redirect("evaluation:index")


@no_login_required
def faq(request):
    return render(request, "faq.html", {"sections": FaqSection.objects.all()})


@no_login_required
def legal_notice(request):
    return render(request, "legal_notice.html")


@require_POST
def contact(request):
    sent_anonymous = request.POST.get("anonymous") == "true"
    if sent_anonymous and not settings.ALLOW_ANONYMOUS_FEEDBACK_MESSAGES:
        raise SuspiciousOperation("Anonymous feedback messages are not allowed, however received one from user!")
    message = request.POST.get("message")
    title = request.POST.get("title")
    if sent_anonymous:
        sender = "anonymous user"
        subject = "[EvaP] Anonymous message"
    else:
        sender = request.user.email or f"User {request.user.id}"
        subject = f"[EvaP] Message from {sender}"
    if message:
        mail = EmailMessage(
            subject=subject,
            body=f"{title}\n{sender}\n\n{message}",
            to=[settings.CONTACT_EMAIL],
            reply_to=[] if sent_anonymous else [sender],
        )
        try:
            mail.send()
            logger.info("Sent contact email: \n%s\n", mail.message())
            return HttpResponse()
        except Exception:
            logger.exception("An exception occurred when sending the following contact email:\n%s\n", mail.message())
            raise

    return HttpResponseBadRequest()


@no_login_required
@require_POST
def set_lang(request):
    if request.user.is_authenticated:
        user = request.user
        user.language = request.POST.get("language", "en")
        user.save()

    return set_language(request)


def profile_edit(request):
    user = request.user
    profile_form = ProfileForm(request.POST or None, request.FILES or None, instance=user)

    if request.method == "POST":
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, _("Successfully updated your profile."))
            return redirect("evaluation:profile_edit")

    editor_context = {
        "delegate_of": user.represented_users.all(),
        "cc_users": user.cc_users.all(),
        "ccing_users": user.ccing_users.all(),
    }

    context = {"user": user, "profile_form": profile_form, **(editor_context if user.is_editor else {})}

    return render(request, "profile.html", context)


@require_POST
def set_notes(request):
    form = NotebookForm(request.POST, instance=request.user)
    if form.is_valid():
        form.save()
        return HttpResponseNoContent()
    return HttpResponseBadRequest()


def set_startpage(request):
    user = request.user
    startpage = request.POST.get("page")
    if startpage not in UserProfile.StartPage.values:
        return HttpResponseBadRequest()
    user.startpage = startpage
    user.save()

    return redirect("evaluation:index")
