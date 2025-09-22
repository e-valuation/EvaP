#!/usr/bin/env python3

import logging
import sys

from django.conf import settings
from django.core.management import execute_from_command_line


def main():
    settings.DATADIR.mkdir(exist_ok=True)

    if settings.TESTING:
        from typeguard import install_import_hook  # pylint: disable=import-outside-toplevel

        install_import_hook(("evap", "tools"))
        logging.disable()

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
