from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.shortcuts import redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.forms import NewKeyForm
from evap.evaluation.models import UserProfile
from evap.fsr.models import EmailTemplate


def index(request):
    new_key_form = NewKeyForm(request.POST or None)
    
    if request.method == 'POST':
        if new_key_form.is_valid():
            # user wants a new login key
            try:
                user = User.objects.get(email__iexact=new_key_form.cleaned_data['email'])
                profile = UserProfile.get_for_user(user)
                profile.generate_logon_key()
                profile.save()
                
                EmailTemplate.get_logon_key_template().send_user(user)
                
            except User.DoesNotExist:
                messages.warning(request, _(u"No user with this e-mail address was found."))
    
    if not request.user.is_active:
        return render_to_response(
            "index.html",
            dict(
                 new_key_form=new_key_form
            ),
            context_instance=RequestContext(request))
    else:
        # redirect user to appropriate start page
        if request.user.is_staff:
            return redirect('evap.fsr.views.index')
        elif UserProfile.get_for_user(request.user).is_contributor:
            return redirect('evap.lecturer.views.index')
        else:
            return redirect('evap.student.views.index')

def login(request):
    # if we already got authentication, e.g. from REMOTE_USER, just go to home
    if request.user.is_authenticated():
        return redirect("/")
    else:
        # otherwise show login form
        if request.method == "POST":
            form = AuthenticationForm(data=request.POST)  
            
            # check user input, uncluding authenticating the user
            if form.is_valid():
                # we succeeded, so log him in
                auth_login(request, form.get_user())

                # clean up our test cookie
                if request.session.test_cookie_worked():
                    request.session.delete_test_cookie()

                return redirect("/")
        else:
            form = AuthenticationForm(request)
        
        # set test cookie to verify whether they work in the next step
        request.session.set_test_cookie()
            
        return render_to_response("login.html", dict(form=form), context_instance=RequestContext(request))


def faq(request):
    return render_to_response("faq.html", dict(), context_instance=RequestContext(request))
