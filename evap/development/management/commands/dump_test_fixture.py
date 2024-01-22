import os

from django.conf import settings
from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import confirm_harmful_operation, logged_call_command


class Command(BaseCommand):
    args = ""
    help = "Drops the database, recreates it and then dumps the after-migration state."

    def handle(self, *args, **options):
        self.stdout.write("")
        self.stdout.write("WARNING! This will drop the database and cause IRREPARABLE DATA LOSS.")
        if not confirm_harmful_operation(self.stdout):
            return

        logged_call_command(self.stdout, "reset_db", interactive=False)

        logged_call_command(self.stdout, "migrate")

        outfile_name = os.path.join(settings.BASE_DIR, "development", "fixtures", "test_with_migrations.json")
        logged_call_command(
            self.stdout,
            "dumpdata",
            indent=2,
            output=outfile_name,
        )

        self.stdout.write("Done.")
