#!/usr/bin/env python3

import os
import sys

from django.conf import settings
from django.core.management import execute_from_command_line


def main():
    assert not settings.configured
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evap.settings")
    settings.DATADIR.mkdir(exist_ok=True)
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
