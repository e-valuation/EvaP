import datetime

from django.core.management.base import BaseCommand
from django.conf import settings

from evap.evaluation.models import Course, EmailTemplate


class Command(BaseCommand):
    args = '<kind of jobs>'
    help = 'Runs updates/tasks based on time events'

    def update_courses(self):
        """ Updates courses state, when evaluation time begins/ends."""
        today = datetime.date.today()

        courses_new_in_evaluation = []

        for course in Course.objects.all():
            try:
                if course.state == "approved" and course.vote_start_date <= today:
                    course.evaluation_begin()
                    course.save()
                    courses_new_in_evaluation.append(course)
                elif course.state == "inEvaluation" and course.vote_end_date < today:
                    course.evaluation_end()
                    if course.is_fully_reviewed():
                        course.review_finished()
                    course.save()
            except Exception:
                pass

        if courses_new_in_evaluation:
            EmailTemplate.get_evaluation_started_template().send_to_users_in_courses(courses_new_in_evaluation, ['all_participants'])

    def check_reminders(self):
        check_dates = []
        for number_of_days in settings.REMIND_X_DAYS_AHEAD_OF_END_DATE:
            check_dates.append(datetime.date.today() + datetime.timedelta(days=number_of_days))
        
        recipients = set()
        for course in Course.objects.filter(state='inEvaluation', vote_end_date__in=check_dates):
            recipients.update(course.due_participants)

        for recipient in recipients:
            due_courses = list(set(Course.objects.filter(participants=recipient, state='inEvaluation').exclude(voters=recipient)))
            due_in_number_of_days = min((course.vote_end_date - datetime.date.today()).days for course in due_courses)
        
            EmailTemplate.send_reminder_to_user(recipient, due_in_number_of_days=due_in_number_of_days, due_courses=due_courses)

    def handle(self, *args, **options):
        if len(args) > 0 and args[0] == 'daily':
            self.check_reminders()
        else:
            self.update_courses()

