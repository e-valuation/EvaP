from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import subprocess_run_or_exit


class Command(BaseCommand):
    args = ""
    help = "Runs the type checker (mypy)"
    requires_migrations_checks = False

    def handle(self, *args, **options):
        subprocess_run_or_exit(["mypy"], self.stdout)
