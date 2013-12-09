from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.shortcuts import redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.forms import NewKeyForm, LoginKeyForm, LoginUsernameForm
from evap.evaluation.models import UserProfile
from evap.fsr.models import EmailTemplate


def index(request):
    """Main entry page into EvaP providing all the login options available. THe username/password 
       login is thought to be used for internal users, e.g. by connecting to a LDAP directory.
       The login key mechanism is meant to be used to include external participants, e.g. visiting 
       students or visiting lecturers.
    """

    # parse the form data into the respective form
    submit_type = request.POST.get("submit_type", "no_submit")
    new_key_form = NewKeyForm(request.POST if submit_type == "new_key" else None)
    login_key_form = LoginKeyForm(request.POST if submit_type == "login_key" else None)
    login_username_form = LoginUsernameForm(request, request.POST if submit_type == "login_username" else None)

    # process form data
    if request.method == 'POST':
        if new_key_form.is_valid():
            # user wants a new login key

            # check if we got a domain user
            if new_key_form.cleaned_data['email'].endswith("hpi.uni-potsdam.de"):
                messages.warning(request, _(u"HPI users cannot request login keys. Please login using your domain credentials."))
            else:
                # non HPI email, send him/her a new logon key
                try:
                    user = User.objects.get(email__iexact=new_key_form.cleaned_data['email'])
                    profile = UserProfile.get_for_user(user)
                    profile.generate_logon_key()
                    profile.save()
                    
                    EmailTemplate.get_logon_key_template().send_user(user)
                    
                    messages.success(request, _(u"Successfully sent email with new login key."))
                except User.DoesNotExist:
                    messages.warning(request, _(u"No user with this e-mail address was found."))
        elif login_key_form.is_valid():
            # user would like to login with a login key and passed key test
            auth_login(request, login_key_form.get_user())
        elif login_username_form.is_valid():
            # user would like to login with username and password and passed password test
            auth_login(request, login_username_form.get_user())

            # clean up our test cookie
            if request.session.test_cookie_worked():
                request.session.delete_test_cookie()
    
    # if not logged in by now, render form
    if not request.user.is_active:
        # set test cookie to verify whether they work in the next step
        request.session.set_test_cookie()

        return render_to_response("index.html", dict(new_key_form=new_key_form, login_key_form=login_key_form, login_username_form=login_username_form), context_instance=RequestContext(request))
    else:
        # redirect user to appropriate start page
        if request.user.is_staff:
            return redirect('evap.fsr.views.index')
        elif UserProfile.get_for_user(request.user).is_lecturer:
            return redirect('evap.lecturer.views.index')
        else:
            return redirect('evap.student.views.index')


def faq(request):
    return render_to_response("faq.html", dict(), context_instance=RequestContext(request))
