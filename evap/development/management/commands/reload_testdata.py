import shutil

from django.conf import settings
from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import confirm_harmful_operation, logged_call_command


class Command(BaseCommand):
    help = "Drops the database, recreates it, and then loads the testdata. Also resets the upload directory."

    def add_arguments(self, parser):
        parser.add_argument("--noinput", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write("")
        self.stdout.write("WARNING! This will drop the database and upload directory and cause IRREPARABLE DATA LOSS.")
        if not options["noinput"] and not confirm_harmful_operation(self.stdout):
            return

        logged_call_command(self.stdout, "reset_db", interactive=False)

        logged_call_command(self.stdout, "migrate")

        # clear any data the migrations created.
        # their pks might differ from the ones in the dump, which results in errors on loaddata
        logged_call_command(self.stdout, "flush", interactive=False)

        logged_call_command(self.stdout, "loaddata", "test_data")

        logged_call_command(self.stdout, "clear_cache", "--all", "-v=1")

        logged_call_command(self.stdout, "refresh_results_cache")

        upload_dir = settings.MEDIA_ROOT
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        shutil.copytree(settings.MODULE / "development" / "fixtures" / "upload", upload_dir)

        self.stdout.write("Done.")
