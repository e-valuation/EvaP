from evap.settings import default, dev, local_services, open_id, test
from evap.settings_resolver import resolve_settings


class LocalSettings:
    DEBUG = True
    SECRET_KEY = "$SECRET_KEY"  # nosec


globals().update(resolve_settings([default, local_services, open_id, dev, test, LocalSettings]))
