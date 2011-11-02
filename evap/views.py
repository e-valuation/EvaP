from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

def index(request):
    return render_to_response(
        "index.html",
        context_instance=RequestContext(request))
