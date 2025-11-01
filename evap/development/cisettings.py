from evap.settings import default, dev, local_services, open_id, test  # noqa: TID251
from evap.settings_resolver import resolve_settings


class CiSettings:
    DEBUG = True
    SECRET_KEY = "evap-github-actions-secret-key"  # nosec


globals().update(resolve_settings([default, open_id, dev, local_services, test, CiSettings]))
