import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "productionsettings")

from evap.wsgi import application  # noqa: F401
