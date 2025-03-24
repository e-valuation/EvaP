from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from evap.evaluation.management.commands.tools import subprocess_run_or_exit


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Watch stylesheets and recompile when they change.",
        )
        parser.add_argument(
            "--production",
            action="store_true",
            help="Compress output stylesheet and do not generate source maps."
            " Intended to use in production deployment.",
        )

    def handle(self, *args, **options):
        static_directory = settings.STATICFILES_DIRS[0]
        command = [
            "npx",
            "sass",
            static_directory / "scss" / "evap.scss",
            static_directory / "css" / "evap.css",
        ]

        if options["watch"]:
            command += ["--watch", "--poll"]

        if options["production"]:
            command += ["--style", "compressed", "--no-source-map"]

        try:
            subprocess_run_or_exit(command, self.stdout)
        except FileNotFoundError as e:
            raise CommandError("Could not find sass command") from e
        except KeyboardInterrupt:
            pass
