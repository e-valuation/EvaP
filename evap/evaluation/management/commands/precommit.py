import subprocess  # nosec
import os.path
import sys

from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    args = ""
    help = "Runs the test suite, linting and formatting. Run this before committing."
    requires_migrations_checks = False

    def handle(self, *args, **options):
        if not os.path.isfile("./manage.py"):
            print("Please call me from the evap root directory (where manage.py resides)")
            sys.exit(1)

        # subprocess call so our sys.argv check in settings.py works
        subprocess.run(["./manage.py", "test"], check=False)  # nosec

        call_command("lint")
        call_command("format")
