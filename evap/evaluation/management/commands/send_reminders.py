import datetime
import logging

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Prefetch
from django.urls import reverse

from evap.evaluation.management.commands.tools import log_exceptions
from evap.evaluation.models import Course, EmailTemplate, Evaluation, Semester
from evap.tools import MonthAndDay, unordered_groupby

logger = logging.getLogger(__name__)


def get_sorted_evaluation_url_tuples_with_urgent_review() -> list[tuple[Evaluation, str]]:
    evaluation_url_tuples: list[tuple[Evaluation, str]] = [
        (
            evaluation,
            settings.PAGE_URL
            + reverse(
                "staff:evaluation_textanswers",
                kwargs={"evaluation_id": evaluation.id},
            ),
        )
        for evaluation in Evaluation.objects.filter(state=Evaluation.State.EVALUATED)
        if evaluation.textanswer_review_state == Evaluation.TextAnswerReviewState.REVIEW_URGENT
    ]
    return sorted(evaluation_url_tuples, key=lambda evaluation_url_tuple: evaluation_url_tuple[0].full_name)


@log_exceptions
class Command(BaseCommand):
    help = "Sends email reminders X days before evaluation ends and reminds managers to review text answers."

    def handle(self, *args, **options):
        logger.info("send_reminders called.")
        self.send_student_reminders()
        self.send_textanswer_reminders()
        self.send_grade_reminders()
        logger.info("send_reminders finished.")

    @staticmethod
    def send_student_reminders():
        check_dates = [
            datetime.date.today() + datetime.timedelta(days=number_of_days)
            for number_of_days in settings.REMIND_X_DAYS_AHEAD_OF_END_DATE
        ]

        recipients = set()
        for evaluation in Evaluation.objects.filter(
            state=Evaluation.State.IN_EVALUATION, vote_end_date__in=check_dates
        ):
            recipients.update(evaluation.due_participants)

        for recipient in recipients:
            due_evaluations = recipient.get_sorted_due_evaluations()

            # entry 0 is first due evaluation, entry 1 in tuple is number of days
            first_due_in_days = due_evaluations[0][1]

            EmailTemplate.send_reminder_to_user(
                recipient, first_due_in_days=first_due_in_days, due_evaluations=due_evaluations
            )
        logger.info("Sent due evaluation reminder emails to %d people.", len(recipients))

    @staticmethod
    def send_textanswer_reminders():
        if datetime.date.today().weekday() in settings.TEXTANSWER_REVIEW_REMINDER_WEEKDAYS:
            evaluation_url_tuples = get_sorted_evaluation_url_tuples_with_urgent_review()
            if not evaluation_url_tuples:
                logger.info("no evaluations require a reminder about text answer review.")
                return

            for manager in Group.objects.get(name="Manager").user_set.all():
                EmailTemplate.send_textanswer_reminder_to_user(manager, evaluation_url_tuples)

            logger.info("sent text answer review reminders.")

    @staticmethod
    def send_grade_reminders():
        today = MonthAndDay(day=datetime.date.today().day, month=datetime.date.today().month)
        if today not in settings.GRADE_REMINDER_EMAIL_DATES:
            return

        courses_without_final_grades = Course.objects_with_missing_final_grades().order_by("name_en")
        semesters = (
            Semester.objects.filter(grade_documents_are_deleted=False)
            .filter(Exists(courses_without_final_grades.filter(semester__pk=OuterRef("pk"))))
            .prefetch_related(
                Prefetch("courses", queryset=courses_without_final_grades, to_attr="courses_without_final_grades"),
            )
        )

        for semester in semesters:
            responsibles_and_courses_without_final_grades = unordered_groupby(
                (responsible, course)
                for course in semester.courses_without_final_grades
                for responsible in course.responsibles.all()
            )

            for recipient in settings.GRADE_REMINDER_EMAIL_RECIPIENTS:
                EmailTemplate.send_grade_reminder(
                    recipient, semester, responsibles_and_courses_without_final_grades.items()
                )

        logger.info(
            "sent grade document reminders for %d semesters to %d people.",
            len(semesters),
            len(settings.GRADE_REMINDER_EMAIL_RECIPIENTS),
        )
