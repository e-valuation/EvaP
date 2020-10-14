import os
import subprocess # nosec

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            '--watch', action='store_true',
            help='Watch stylesheets and recompile when they change.',
        )

    def handle(self, *args, **options):
        static_directory = settings.STATICFILES_DIRS[0]
        command = [
            'sass',
            os.path.join(static_directory, 'scss', 'evap.scss'),
            os.path.join(static_directory, 'css', 'evap.css'),
        ]

        if options['watch']:
            command += ['--watch', '--poll']

        try:
            subprocess.run(command, check=True) # nosec
        except FileNotFoundError:
            print('Could not find sass command', file=self.stderr)
        except KeyboardInterrupt:
            pass
