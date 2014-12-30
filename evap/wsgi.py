"""
WSGI config for EvaP project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.7/howto/deployment/wsgi/
"""

import os
import sys

# this adds the project root to the python path.
pwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path = [pwd] + sys.path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evap.settings")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
