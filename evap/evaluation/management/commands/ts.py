import argparse
import os
import subprocess  # nosec
import unittest

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test.runner import DiscoverRunner


class RenderPagesRunner(DiscoverRunner):
    """Test runner which only includes `render_pages.*` methods.
    The actual logic of the page rendering is implemented in the `@render_pages` decorator."""

    test_loader = unittest.TestLoader()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.test_loader.testMethodPrefix = "render_pages"


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
        subparsers.add_parser("render_pages")

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
        elif options["command"] == "render_pages":
            self.render_pages(**options)

    def run_command(self, command):
        try:
            subprocess.run(command, check=True)  # nosec
        except FileNotFoundError as e:
            raise CommandError(f"Could not find {command[0]} command") from e
        except KeyboardInterrupt:
            pass
        except subprocess.CalledProcessError as e:
            raise CommandError("Error during command execution", returncode=e.returncode) from e

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

    def test(self, **options):
        call_command("scss")
        self.compile(**options)
        self.render_pages()
        self.run_command(["npx", "jest"])

    @staticmethod
    def render_pages(**_options):
        # Enable debug mode as otherwise a collectstatic beforehand would be necessary,
        # as missing static files would result into an error.
        test_runner = RenderPagesRunner(debug_mode=True)
        failed_tests = test_runner.run_tests([])
        if failed_tests > 0:
            raise CommandError("Failures during render_pages")
