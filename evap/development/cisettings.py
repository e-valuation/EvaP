from evap.settings import default, dev, local_services, open_id
from evap.settings_resolver import resolve_settings


class CiSettings:
    DEBUG = True
    SECRET_KEY = "github-actions-evap"  # nosec


globals().update(resolve_settings([default, open_id, dev, local_services, CiSettings]))
