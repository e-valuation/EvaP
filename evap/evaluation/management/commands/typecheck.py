from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import run_exit_if_nonzero_return_code


class Command(BaseCommand):
    args = ""
    help = "Runs the type checker (mypy)"
    requires_migrations_checks = False

    def handle(self, *args, **options):
        run_exit_if_nonzero_return_code(["mypy"])
