from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import ugettext as _

from evap.evaluation.models import Semester, LikertAnswer

class Command(BaseCommand):
    args = '<name of statistic> <semester id>'
    help = 'Computes statstics over semesters'

    def answer_histogram(self):
        import matplotlib.pyplot as plt

        answers = LikertAnswer.objects.filter(contribution__course__semester=self.semester)

        fig = plt.figure()
        ax = fig.add_subplot(111)

        # the histogram of the data
        ax.hist([answer.answer for answer in answers], bins=[0.5,1.5,2.5,3.5,4.5])

        ax.set_ylabel('Answers')
        ax.set_ylabel('Grade')
        ax.grid(True)
        plt.show()

    def handle(self, *args, **options):
        if len(args) != 2:
            raise CommandError(_("Wrong arguments given."))

        statistic = args[0]
        semester_id = args[1]

        # get semester
        try:
            self.semester = Semester.objects.get(pk=semester_id)
        except Semester.DoesNotExist:
            raise CommandError(_("Supplied semester does not exist."))

        # get statistic
        if not hasattr(self, statistic):
            raise CommandError(_("Supplied statistic does not exist."))

        # execute it
        getattr(self, statistic)()
