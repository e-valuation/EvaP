from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = ""
    help = 'Execute "makemessages --locale=de --ignore=node_modules/*"'

    def handle(self, *args, **options):
        self.stdout.write('Executing "manage.py makemessages --locale=de --ignore=node_modules/*"')
        call_command("makemessages", "--locale=de", "--ignore=node_modules/*")
        call_command(
            "makemessages",
            "--domain=djangojs",
            "--extension=js,ts",
            "--locale=de",
            "--ignore=node_modules/*",
            "--ignore=evap/static/js/*.min.js",
        )
