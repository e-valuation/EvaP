from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key

from evap.evaluation.models import UserProfile

import urllib.parse


def custom_redirect(url_name, *args, **kwargs):
    url = reverse(url_name, args=args)
    params = urllib.parse.urlencode(kwargs)
    return HttpResponseRedirect(url + "?%s" % params)

def delete_navbar_cache():
    # delete navbar cache from base.html
    for user in UserProfile.objects.all():
        key = make_template_fragment_key('navbar', [user.username, 'de'])
        cache.delete(key)
        key = make_template_fragment_key('navbar', [user.username, 'en'])
        cache.delete(key)
