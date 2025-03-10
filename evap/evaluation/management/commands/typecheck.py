import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = "Runs the type checker (mypy)"
    requires_migrations_checks = False

    def handle(self, *args, **options):
        sys.exit(subprocess.run(["mypy"], check=False).returncode)
