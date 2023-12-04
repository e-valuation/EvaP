from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import logged_call_command


class Command(BaseCommand):
    args = ""
    help = 'Execute "makemessages --locale=de --ignore=node_modules/*"'

    def handle(self, *args, **options):
        logged_call_command(self.stdout, "makemessages", "--locale=de", "--ignore=node_modules/*")
        logged_call_command(
            self.stdout,
            "makemessages",
            "--domain=djangojs",
            "--extension=js,ts",
            "--locale=de",
            "--ignore=node_modules/*",
            "--ignore=evap/static/js/*.min.js",
        )
