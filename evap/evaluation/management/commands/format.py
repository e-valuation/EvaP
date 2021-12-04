import subprocess  # nosec

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = "Runs the code formatter"
    requires_migrations_checks = False

    def handle(self, *args, **options):
        subprocess.run(["black", "evap"], check=False)  # nosec
        subprocess.run(["isort", "."], check=False)  # nosec
        subprocess.run(["npx", "prettier", "--write", "evap/static/ts/src"], check=False)  # nosec
