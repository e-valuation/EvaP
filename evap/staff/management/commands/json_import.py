import logging

from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import log_exceptions
from evap.evaluation.models import Semester
from evap.staff.importers.json import JSONImporter

logger = logging.getLogger(__name__)


@log_exceptions
class Command(BaseCommand):
    help = "Import enrollments from JSON file."

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument("semester", type=int)
        parser.add_argument("file", type=str)
        parser.add_argument("default_course_end", type=str)

    def handle(self, *args, **options):
        try:
            semester = Semester.objects.get(pk=options["semester"])
        except Semester.DoesNotExist:
            self.stdout.write(self.style.ERROR("Semester does not exist."))
            return

        with open(options["file"]) as file:
            JSONImporter(semester, options["default_course_end"]).import_json(file.read())
