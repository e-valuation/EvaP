import sys

from django.core.management.base import BaseCommand
from django.core.management import execute_from_command_line


class Command(BaseCommand):
    args = ''
    help = 'Execute "runserver 0.0.0.0:8000"'

    def handle(self, *args, **options):
        self.stdout.write('Executing "manage.py runserver 0.0.0.0:8000"')
        sys.argv = ["manage.py", "runserver", "0.0.0.0:8000"]
        execute_from_command_line(sys.argv)
