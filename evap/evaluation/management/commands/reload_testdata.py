from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    args = ''
    help = 'Drops the database, recreates it and then loads the testdata.'

    def handle(self, *args, **options):
        print("")
        print("WARNING! This will drop the database and cause IRREPARABLE DATA LOSS.")
        if input("Are you sure you want to continue? (yes/no)") != "yes":
            print("Aborting...")
            return
        print("")
        if not settings.DEBUG:
            print("DEBUG is disabled. Are you sure you are not running")
            if input("on a production system and want to continue? (yes/no)") != "yes":
                print("Aborting...")
                return
            print("")

        print('Executing "python manage.py reset_db"')
        call_command("reset_db", user='evap', interactive=False)

        print('Executing "python manage.py migrate"')
        call_command("migrate")

        print('Executing "python manage.py createcachetable"')
        call_command("createcachetable")

        print('Executing "python manage.py load_testdata"')
        call_command("loaddata", "test_data")

        print('Done.')
