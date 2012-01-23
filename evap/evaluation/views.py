from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.forms import NewKeyForm
from evap.fsr.models import EmailTemplate


class HttpResponseUnauthorized(HttpResponse):
    status_code = 401


def index(request):
    new_key_form = NewKeyForm(request.POST or None)
    
    if request.method == 'POST':
        if new_key_form.is_valid():
            # user wants a new login key
            try:
                user = User.objects.get(email__iexact=new_key_form.cleaned_data['email'])
                profile = user.get_profile()
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
        elif request.user.get_profile().is_lecturer:
            return redirect('evap.lecturer.views.index')
        else:
            return redirect('evap.student.views.index')


def logout(request):
    auth_logout(request)
    response = render_to_response("logout.html", context_instance=RequestContext(request))
    response.status_code = 401
    return response


def faq(request):
    return render_to_response("faq.html", dict(), context_instance=RequestContext(request))
