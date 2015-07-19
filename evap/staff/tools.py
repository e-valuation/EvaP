from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect

import urllib.parse


def custom_redirect(url_name, *args, **kwargs):
    url = reverse(url_name, args=args)
    params = urllib.parse.urlencode(kwargs)
    return HttpResponseRedirect(url + "?%s" % params)
