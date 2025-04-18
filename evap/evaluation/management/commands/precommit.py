import os.path
import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import subprocess_run_or_exit


class Command(BaseCommand):
    args = ""
    help = "Runs the test suite, linting and formatting. Run this before committing."
    requires_migrations_checks = False

    def handle(self, *args, **options):
        if not os.path.isfile("./manage.py"):
            self.stdout.write("Please call me from the evap root directory (where manage.py resides)")
            sys.exit(1)

        call_command("typecheck")

        # subprocess call so our sys.argv check in settings.py works
        subprocess_run_or_exit(["./manage.py", "test"], self.stdout)

        call_command("format")
        call_command("lint")
