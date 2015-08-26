from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command

from io import StringIO
import os
import json


class Command(BaseCommand):
    args = ''
    help = 'Dumps the contents of the database into test_data.json. Output is sorted to produce smaller diffs.'

    def handle(self, *args, **options):
        out = StringIO()
        call_command("dumpdata", "auth.group", "evaluation", "rewards", "grades", stdout=out)

        j = json.loads(out.getvalue())
        # sort lists
        for obj in j:
            for fieldname, fieldcontent in obj["fields"].items():
                if type(fieldcontent) is list:
                    obj["fields"][fieldname] = sorted(fieldcontent)
        # dicts are sorted here
        dump = json.dumps(j, sort_keys=True, indent=2)

        outfile = open(os.path.join(settings.BASE_DIR, "evaluation", "fixtures", "test_data.json"), "w")

        outfile.write(dump)
