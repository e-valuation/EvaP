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

        # get semester
        try:
            self.semester = Semester.objects.get(pk=semester_id)
        except Semester.DoesNotExist:
            raise CommandError(_("Supplied semester does not exist."))

        for course in self.semester.course_set.all():
            if course.participants.exists():
                course.participant_count = course.participants.count()
                course.participants.clear()

            if course.voters.exists():
                course.voter_count = course.voters.count()
                course.voters.clear()

            course.save()
