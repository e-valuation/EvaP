from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect

from evap.evaluation.models import Semester

import urllib

def menu_semesters():
    semesters = Semester.objects.all()[:5]
    return {'semesters': semesters}


def custom_redirect(url_name, *args, **kwargs):
    url = reverse(url_name, args = args)
    params = urllib.urlencode(kwargs)
    return HttpResponseRedirect(url + "?%s" % params)
