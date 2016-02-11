import datetime
import operator
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from evap.evaluation.models import Course, EmailTemplate

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sends email reminders X days before course evaluation ends.'

    def handle(self, *args, **options):
        logger.info("send_reminders called.")
        check_dates = []

        # Collect end-dates of courses whose participants need to be reminded today.
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

            # Sort courses by number of days left for evaluation and bring them to following format:
            # [(course, due_in_days), ...]
            due_courses = sorted(due_courses.items(), key=operator.itemgetter(1))

            EmailTemplate.send_reminder_to_user(recipient, first_due_in_days=first_due_in_days, due_courses=due_courses)
        logger.info("send_reminders finished.")
        logger.info("sent reminders to %s people." % len(recipients))
