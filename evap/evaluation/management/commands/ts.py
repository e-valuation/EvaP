import argparse

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from evap.evaluation.management.commands.tools import subprocess_run_or_exit


class Command(BaseCommand):
    def add_arguments(self, parser: argparse.ArgumentParser):
        subparsers = parser.add_subparsers(dest="command", required=True)
        compile_parser = subparsers.add_parser("compile")
        compile_parser.add_argument(
            "--watch",
            action="store_true",
            help="Watch scripts and recompile when they change.",
        )
        self.add_fresh_argument(compile_parser)
        test_parser = subparsers.add_parser("test")
        self.add_fresh_argument(test_parser)

    @staticmethod
    def add_fresh_argument(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Delete .tsbuildinfo.json before compilation to force a fresh compilation."
            "This is useful when incremental compilation does not yield the expected output.",
        )

    def handle(self, *args, **options):
        if options["command"] == "compile":
            self.compile(**options)
        elif options["command"] == "test":
            self.test(**options)

    def run_command(self, command):
        try:
            subprocess_run_or_exit(command, self.stdout)
        except FileNotFoundError as e:
            raise CommandError(f"Could not find {command[0]} command") from e
        except KeyboardInterrupt:
            pass

    def compile(self, watch=False, fresh=False, **_options):
        static_directory = settings.STATICFILES_DIRS[0]
        command = [
            "npx",
            "tsc",
            "--project",
            static_directory / "ts" / "tsconfig.compile.json",
        ]

        if watch:
            command += ["--watch"]

        if fresh:
            (static_directory / "ts" / ".tsbuildinfo.json").unlink(missing_ok=True)

        self.run_command(command)

    def test(self, **options):
        call_command("scss")
        self.compile(**options)
        self.run_command(["npx", "jest"])
