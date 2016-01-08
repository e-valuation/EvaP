from django.core.management.base import BaseCommand
from django.core.management import execute_from_command_line

import sys


class Command(BaseCommand):
    args = ''
    help = 'Execute "runserver 0.0.0.0:80"'

    def handle(self, *args, **options):
        print('Executing "manage.py runserver 0.0.0.0:8000"')
        sys.argv = ["manage.py", "runserver", "0.0.0.0:8000"]
        execute_from_command_line(sys.argv)
