import subprocess  # nosec

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = "Runs code formatting"
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "formatter", nargs="?", choices=["black", "isort", "prettier", "python"], help="Specify a formatter to run."
        )

    def run_black(self):
        self.stdout.write("Executing black .")
        subprocess.run(["black", "."], check=False)  # nosec

    def run_isort(self):
        self.stdout.write("Executing isort .")
        subprocess.run(["isort", "."], check=False)  # nosec

    def run_prettier(self):
        self.stdout.write("Executing npx prettier")
        subprocess.run(["npx", "prettier", "--write", "evap/static/ts/**/*.ts"], check=False)  # nosec

    def handle(self, *args, **options):
        if options["formatter"] in ("black", "python", None):
            self.run_black()
        if options["formatter"] in ("isort", "python", None):
            self.run_isort()
        if options["formatter"] in ("prettier", None):
            self.run_prettier()
