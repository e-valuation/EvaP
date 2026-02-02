import subprocess  # nosec

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = "Runs code formatting"
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "formatter", nargs="?", choices=["ruff", "prettier", "python"], help="Specify a formatter to run."
        )

    def run_ruff(self):
        self.stdout.write("Executing ruff format .")
        subprocess.run(["ruff", "format", "."], check=False)  # nosec
        self.stdout.write("Executing ruff check --select I --fix .")
        subprocess.run(["ruff", "check", "--select", "I", "--fix", "."], check=False)  # nosec

    def run_prettier(self):
        self.stdout.write("Executing npx prettier")
        subprocess.run(["npx", "prettier", "--write", "evap/static/ts/**/*.ts"], check=False)  # nosec

    def handle(self, *args, **options):
        if options["formatter"] in ("ruff", "python", None):
            self.run_ruff()
        if options["formatter"] in ("prettier", None):
            self.run_prettier()
