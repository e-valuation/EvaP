from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    args = ''
    help = 'Drops the database, recreates it and then loads the testdata.'

    def handle(self, *args, **options):
        self.stdout.write("")
        self.stdout.write("WARNING! This will drop the database and cause IRREPARABLE DATA LOSS.")
        if input("Are you sure you want to continue? (yes/no)") != "yes":
            self.stdout.write("Aborting...")
            return
        self.stdout.write("")
        if not settings.DEBUG:
            self.stdout.write("DEBUG is disabled. Are you sure you are not running")
            if input("on a production system and want to continue? (yes/no)") != "yes":
                self.stdout.write("Aborting...")
                return
            self.stdout.write("")

        self.stdout.write('Executing "python manage.py reset_db"')
        call_command("reset_db", user='evap', interactive=False)

        self.stdout.write('Executing "python manage.py migrate"')
        call_command("migrate")

        self.stdout.write('Executing "python manage.py createcachetable"')
        call_command("createcachetable")

        self.stdout.write('Executing "python manage.py load_testdata"')
        call_command("loaddata", "test_data")

        self.stdout.write('Executing "python manage.py refresh_results_cache"')
        call_command("refresh_results_cache")

        self.stdout.write('Done.')
