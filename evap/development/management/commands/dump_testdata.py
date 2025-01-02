import os

from django.conf import settings
from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import logged_call_command


class Command(BaseCommand):
    args = ""
    help = "Dumps all relevant contents of the database into test_data.json."
    requires_migrations_checks = True

    def handle(self, *args, **options):
        outfile_name = os.path.join(settings.MODULE, "development", "fixtures", "test_data.json")
        logged_call_command(
            self.stdout,
            "dumpdata",
            "auth.group",
            "evaluation",
            "rewards",
            "student",
            "grades",
            "--exclude=evaluation.LogEntry",
            indent=2,
            output=outfile_name,
            natural_foreign=True,
            natural_primary=True,
        )
