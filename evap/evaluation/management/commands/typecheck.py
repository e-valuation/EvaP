import subprocess  # nosec

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = "Runs the type checker (mypy)"
    requires_migrations_checks = False

    def handle(self, *args, **options):
        subprocess.run(["mypy"], check=True)  # nosec
