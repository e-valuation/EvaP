import sys

from django.core.management import execute_from_command_line
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = 'Execute "runserver 0.0.0.0:8000"'

    def handle(self, *args, **options):
        self.stdout.write('Executing "manage.py scss"')
        execute_from_command_line(["manage.py", "scss"])
        self.stdout.write('Executing "manage.py ts compile"')
        execute_from_command_line(["manage.py", "ts", "compile"])
        self.stdout.write('Executing "manage.py runserver 0.0.0.0:8000"')
        sys.argv = ["manage.py", "runserver", "0.0.0.0:8000"]
        execute_from_command_line(sys.argv)
