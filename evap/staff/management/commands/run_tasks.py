import datetime
import operator
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from evap.evaluation.models import Course, EmailTemplate

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = '<kind of jobs>'
    help = 'Runs updates/tasks based on time events'

    def update_courses(self):
        """ Updates courses state, when evaluation time begins/ends."""
        Course.update_courses()

    def check_reminders(self):
        logger.info("check_reminders called.")
        check_dates = []
        for number_of_days in settings.REMIND_X_DAYS_AHEAD_OF_END_DATE:
            check_dates.append(datetime.date.today() + datetime.timedelta(days=number_of_days))

        recipients = set()
        for course in Course.objects.filter(state='inEvaluation', vote_end_date__in=check_dates):
            recipients.update(course.due_participants)

        for recipient in recipients:
            due_courses = dict()
            for course in Course.objects.filter(participants=recipient, state='inEvaluation').exclude(voters=recipient):
                due_courses[course] = (course.vote_end_date - datetime.date.today()).days
            first_due_in_days = min(due_courses.values())
            # sort courses by number of days left for evaluation and bring them to following format: [(course, due_in_days), ...]
            due_courses = sorted(due_courses.items(), key=operator.itemgetter(1))

            EmailTemplate.send_reminder_to_user(recipient, first_due_in_days=first_due_in_days, due_courses=due_courses)
        logger.info("check_reminders finished.")

    def handle(self, *args, **options):
        if len(args) > 0 and args[0] == 'daily':
            self.check_reminders()
        else:
            self.update_courses()
