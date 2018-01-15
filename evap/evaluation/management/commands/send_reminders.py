import datetime
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from evap.evaluation.models import Course, EmailTemplate
from evap.evaluation.management.commands.tools import log_exceptions
from evap.evaluation.tools import get_due_courses_for_user

logger = logging.getLogger(__name__)


@log_exceptions
class Command(BaseCommand):
    help = 'Sends email reminders X days before course evaluation ends.'

    def handle(self, *args, **options):
        logger.info("send_reminders called.")
        check_dates = []

        # Collect end-dates of courses whose participants need to be reminded today.
        for number_of_days in settings.REMIND_X_DAYS_AHEAD_OF_END_DATE:
            check_dates.append(datetime.date.today() + datetime.timedelta(days=number_of_days))

        recipients = set()
        for course in Course.objects.filter(state='in_evaluation', vote_end_date__in=check_dates):
            recipients.update(course.due_participants)

        for recipient in recipients:
            due_courses = get_due_courses_for_user(recipient)
            first_due_in_days = due_courses[0][1]  # entry 0 is first due course, entry 1 in tuple is number of days

            EmailTemplate.send_reminder_to_user(recipient, first_due_in_days=first_due_in_days, due_courses=due_courses)
        logger.info("send_reminders finished.")
        logger.info("sent reminders to {} people.".format(len(recipients)))
