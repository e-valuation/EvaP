#!/usr/bin/env python3

import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evap.settings")

    from django.conf import settings
    from django.core.management import execute_from_command_line

    settings.DATADIR.mkdir(exist_ok=True)
    execute_from_command_line(sys.argv)
