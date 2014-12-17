from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import ugettext as _

from evap.evaluation.models import Semester


class Command(BaseCommand):
    args = '<semester id>'
    help = 'Removes all participant and voter information from the DB.'

    def handle(self, *args, **options):
        if len(args) != 1:
            raise CommandError(_("Wrong arguments given."))

        semester_id = args[0]

        semester = None
        try:
            semester = Semester.objects.get(pk=semester_id)
        except Semester.DoesNotExist:
            raise CommandError(_("Supplied semester does not exist."))

        semester.archive()
