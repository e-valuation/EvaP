from django.core.urlresolvers import reverse 
from django.http import HttpResponseRedirect

from evap.evaluation.models import Semester, Questionnaire

import urllib

def all_semesters():
    semesters = Semester.objects.all()
    return {'semesters': semesters}


def all_questionnaires():
    questionnaires = Questionnaire.objects.filter(obsolete=False)
    return {'questionnaires': questionnaires}

def custom_redirect(url_name, *args, **kwargs):
    url = reverse(url_name, args = args)
    params = urllib.urlencode(kwargs)
    return HttpResponseRedirect(url + "?%s" % params)
