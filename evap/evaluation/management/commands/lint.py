import subprocess  # nosec

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = "Runs the code linter"
    requires_migrations_checks = False

    def handle(self, *args, **options):
        print("Executing ruff .")
        subprocess.run(["ruff", "."], check=False)  # nosec
        print("Executing pylint evap")
        subprocess.run(["pylint", "evap"], check=False)  # nosec
