from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.forms import NewKeyForm
from evap.fsr.models import EmailTemplate

def index(request):
    new_key_form = NewKeyForm(request.POST or None)
    
    if request.method == 'POST':
        if new_key_form.is_valid():
            try:
                user = User.objects.get(email__iexact=new_key_form.cleaned_data['email'])
                profile = user.get_profile()
                profile.generate_logon_key()
                profile.save()
                
                EmailTemplate.get_logon_key_template().send_user(user)
                
            except User.DoesNotExist:
                messages.warning(request, _(u"No user with this e-mail address was found."))
    
    return render_to_response(
        "index.html",
        dict(
             new_key_form=new_key_form
        ),
        context_instance=RequestContext(request))
