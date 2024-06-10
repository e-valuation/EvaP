import subprocess  # nosec

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = "Runs code formatting"
    requires_migrations_checks = False

    def handle(self, *args, **options):
        subprocess.run(["black", "."], check=False)  # nosec
        subprocess.run(["isort", "."], check=False)  # nosec
        subprocess.run(["npx", "prettier", "--write", "evap/static/ts/**/*.ts"], check=False)  # nosec
