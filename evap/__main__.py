#!/usr/bin/env python3

import os
import sys

from django.core.management import execute_from_command_line


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evap.settings")
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
