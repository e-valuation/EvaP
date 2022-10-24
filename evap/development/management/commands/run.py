import sys
from subprocess import Popen  # nosec

from django.core.management import execute_from_command_line
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = 'Execute "runserver 0.0.0.0:8000"'

    def handle(self, *args, **options):
        self.stdout.write('Executing "manage.py scss" and "manage.py ts compile"')
        with Popen(["./manage.py", "scss"]), Popen(["./manage.py", "ts", "compile"]):  # nosec
            self.stdout.write('Executing "manage.py runserver 0.0.0.0:8000"')
            sys.argv = ["manage.py", "runserver", "0.0.0.0:8000"]
            execute_from_command_line(sys.argv)
