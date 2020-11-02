import argparse
import os
import subprocess  # nosec
import sys

from django.conf import settings
from django.core.management.base import BaseCommand


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

    def run_command(self, command):
        try:
            subprocess.run(command, check=True)  # nosec
        except FileNotFoundError:
            print(f"Could not find {command[0]} command", file=self.stderr)
        except KeyboardInterrupt:
            pass
        except subprocess.CalledProcessError as error:
            sys.exit(error.returncode)

    def compile(self, watch=False, fresh=False, **_options):
        static_directory = settings.STATICFILES_DIRS[0]
        command = [
            "npx",
            "tsc",
            "--project",
            os.path.join(static_directory, "ts", "tsconfig.compile.json"),
        ]

        if watch:
            command += ["--watch"]

        if fresh:
            try:
                os.remove(os.path.join(static_directory, "ts", ".tsbuildinfo.json"))
            except FileNotFoundError:
                pass

        self.run_command(command)
