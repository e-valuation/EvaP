from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import confirm_harmful_operation, logged_call_command


class Command(BaseCommand):
    args = ""
    help = "Drops the database, recreates it and then loads the testdata."

    def handle(self, *args, **options):
        self.stdout.write("")
        self.stdout.write("WARNING! This will drop the database and cause IRREPARABLE DATA LOSS.")
        if not confirm_harmful_operation(self.stdout):
            return

        logged_call_command(self.stdout, "reset_db", interactive=False)

        logged_call_command(self.stdout, "migrate")

        # clear any data the migrations created.
        # their pks might differ from the ones in the dump, which results in errors on loaddata
        logged_call_command(self.stdout, "flush", interactive=False)

        logged_call_command(self.stdout, "loaddata", "test_data")

        logged_call_command(self.stdout, "clear_cache", "--all", "-v=1")

        logged_call_command(self.stdout, "refresh_results_cache")

        self.stdout.write("Done.")
