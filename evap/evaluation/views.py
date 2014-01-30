from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.shortcuts import redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.forms import NewKeyForm, LoginKeyForm, LoginUsernameForm
from evap.evaluation.models import UserProfile, FaqSection
from evap.fsr.models import EmailTemplate


def index(request):
    """Main entry page into EvaP providing all the login options available. THe username/password 
       login is thought to be used for internal users, e.g. by connecting to a LDAP directory.
       The login key mechanism is meant to be used to include external participants, e.g. visiting 
       students or visiting contributors.
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
            profile = new_key_form.get_profile()
            profile.generate_login_key()
            profile.save()
            
            EmailTemplate.get_login_key_template().send_user(new_key_form.get_user())
            
            messages.success(request, _(u"Successfully sent email with new login key."))
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
        # check for redirect variable
        next = request.GET.get("next", None)
        if not next is None:
            if next.startswith("/fsr/"):
                if request.user.is_staff:
                    return redirect(next)
            elif next.startswith("/contributor/"):
                if UserProfile.get_for_user(request.user).is_contributor:
                    return redirect(next)
            else:
                return redirect(next)

        # redirect user to appropriate start page
        if request.user.is_staff:
            return redirect('evap.fsr.views.index')
        elif UserProfile.get_for_user(request.user).is_editor_or_delegate:
            return redirect('evap.contributor.views.index')
        else:
            return redirect('evap.student.views.index')


def faq(request):    
    return render_to_response("faq.html", dict(sections=FaqSection.objects.all()), context_instance=RequestContext(request))
