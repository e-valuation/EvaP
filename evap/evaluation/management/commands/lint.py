import subprocess  # nosec

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = "Runs the code linter"
    requires_migrations_checks = False

    def handle(self, *args, **options):
        self.stdout.write("Executing ruff .")
        subprocess.run(["ruff", "check", "."], check=False)  # nosec
        self.stdout.write("Executing pylint evap")
        subprocess.run(["pylint", "evap", "tools"], check=False)  # nosec
