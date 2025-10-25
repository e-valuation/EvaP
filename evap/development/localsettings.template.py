# noqa: N999

from evap.settings import debug_toolbar, default, dev, local_services, open_id, test  # noqa: TID251
from evap.settings_resolver import resolve_settings


class LocalSettings:
    DEBUG = True
    SECRET_KEY = "$SECRET_KEY"  # nosec


globals().update(resolve_settings([default, local_services, open_id, dev, test, debug_toolbar, LocalSettings]))
