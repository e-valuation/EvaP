import datetime
from django.core import management, mail
from unittest.mock import patch
from django.test import TestCase
from django.test.utils import override_settings
from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course


class TestUpdateCourseStatesCommand(TestCase):
    def test_update_courses_called(self):
        with patch('evap.evaluation.models.Course.update_courses') as mock:
            management.call_command('update_course_states')

        self.assertEquals(mock.call_count, 1)


@override_settings(REMIND_X_DAYS_AHEAD_OF_END_DATE=[0, 2])
class TestSendRemindersCommand(TestCase):
    today = datetime.date.today()

    def test_remind_user_about_one_course(self):
        user_to_remind = mommy.make(UserProfile)
        course = mommy.make(
                Course,
                state='inEvaluation',
                vote_start_date=self.today - datetime.timedelta(days=1),
                vote_end_date=self.today + datetime.timedelta(days=2),
                participants=[user_to_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEquals(mock.call_count, 1)
        mock.assert_called_once_with(user_to_remind, first_due_in_days=2, due_courses=[(course, 2)])

    def test_remind_user_once_about_two_courses(self):
        user_to_remind = mommy.make(UserProfile)
        course1 = mommy.make(
                Course,
                state='inEvaluation',
                vote_start_date=self.today - datetime.timedelta(days=1),
                vote_end_date=self.today + datetime.timedelta(days=0),
                participants=[user_to_remind])
        course2 = mommy.make(
                Course,
                state='inEvaluation',
                vote_start_date=self.today - datetime.timedelta(days=1),
                vote_end_date=self.today + datetime.timedelta(days=2),
                participants=[user_to_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEquals(mock.call_count, 1)
        mock.assert_called_once_with(user_to_remind, first_due_in_days=0, due_courses=[(course1, 0), (course2, 2)])

    def test_dont_remind_already_voted(self):
        user_no_remind = mommy.make(UserProfile)
        mommy.make(
                Course,
                state='inEvaluation',
                vote_start_date=self.today - datetime.timedelta(days=1),
                vote_end_date=self.today + datetime.timedelta(days=2),
                participants=[user_no_remind],
                voters=[user_no_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEqual(mock.call_count, 0)
        self.assertEqual(len(mail.outbox), 0)
