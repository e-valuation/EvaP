import subprocess  # nosec
from argparse import ArgumentParser

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Runs the code linter"
    requires_migrations_checks = False

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "linter", nargs="?", choices=["ruff", "pylint", "eslint", "python"], help="Specify a linter to run."
        )

    def run_ruff(self) -> None:
        self.stdout.write("Executing ruff check .")
        subprocess.run(["ruff", "check", "."], check=False)  # nosec

    def run_pylint(self) -> None:
        self.stdout.write("Executing pylint evap")
        subprocess.run(["pylint", "evap", "tools"], check=False)  # nosec

    def run_eslint(self) -> None:
        self.stdout.write("Executing npx eslint --quiet")
        subprocess.run(["npx", "eslint", "--quiet"], cwd="evap/static/ts", check=False)  # nosec

    def handle(self, *args, **options) -> None:
        if options["linter"] in ("ruff", "python", None):
            self.run_ruff()
        if options["linter"] in ("pylint", "python", None):
            self.run_pylint()
        if options["linter"] in ("eslint", None):
            self.run_eslint()
