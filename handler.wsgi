import os
import sys

os.environ['DJANGO_SETTINGS_MODULE'] = 'evap.settings'
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

import django.core.handlers.wsgi
_application = django.core.handlers.wsgi.WSGIHandler()

def application(environ, start_response):
        if 'HTTP_X_FORWARDED_PROTOCOL' in environ:
                environ['wsgi.url_scheme'] = environ.get('HTTP_X_FORWARDED_PROTOCOL', 'http')
        if 'HTTP_X_FORWARDED_HOST' in environ:
                environ['HTTP_X_FORWARDED_HOST'] = environ['HTTP_X_FORWARDED_HOST'].split(',')[0].strip()
        return _application(environ, start_response)
