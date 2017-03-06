import datetime
import os
from unittest.mock import patch

from django.conf import settings
from django.utils.six import StringIO
from django.core import management, mail
from django.test import TestCase
from django.test.utils import override_settings

from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Semester


class TestAnonymizeCommand(TestCase):
    @patch('builtins.input')
    def test_anonymize_does_not_crash(self, mock_input):
        semester = mommy.make(Semester)
        mommy.make(Course, semester=semester)
        mock_input.return_value = 'yes'

        management.call_command('anonymize', stdout=StringIO())


class TestRunCommand(TestCase):
    def test_calls_runserver(self):
        args = ["manage.py", "runserver", "0.0.0.0:8000"]
        with patch('django.core.management.execute_from_command_line') as mock:
            management.call_command('run', stdout=StringIO())

        mock.assert_called_once_with(args)


class TestReloadTestdataCommand(TestCase):
    @patch('builtins.input')
    @patch('evap.evaluation.management.commands.reload_testdata.call_command')
    def test_aborts(self, mock_call_command, mock_input):
        mock_input.return_value = 'not yes'

        management.call_command('reload_testdata', stdout=StringIO())

        self.assertEqual(mock_call_command.call_count, 0)

    @patch('builtins.input')
    @patch('evap.evaluation.management.commands.reload_testdata.call_command')
    def test_executes_key_commands(self, mock_call_command, mock_input):
        mock_input.return_value = 'yes'

        management.call_command('reload_testdata', stdout=StringIO())

        mock_call_command.assert_any_call('reset_db', user='evap', interactive=False)
        mock_call_command.assert_any_call('migrate')
        mock_call_command.assert_any_call('createcachetable')
        mock_call_command.assert_any_call('loaddata', 'test_data')

        self.assertEqual(mock_call_command.call_count, 4)


class TestRefreshResultsCacheCommand(TestCase):
    def test_calls_calculate_results(self):
        mommy.make(Course)
        with patch('evap.evaluation.tools.calculate_results') as mock:
            management.call_command('refresh_results_cache', stdout=StringIO())

        self.assertEqual(mock.call_count, Course.objects.count())


class TestUpdateCourseStatesCommand(TestCase):
    def test_update_courses_called(self):
        with patch('evap.evaluation.models.Course.update_courses') as mock:
            management.call_command('update_course_states')

        self.assertEqual(mock.call_count, 1)


class TestDumpTestDataCommand(TestCase):
    def test_dumpdata_called(self):
        with patch('evap.evaluation.management.commands.dump_testdata.call_command') as mock:
            management.call_command('dump_testdata')

        outfile_name = os.path.join(settings.BASE_DIR, "evaluation", "fixtures", "test_data.json")
        mock.assert_called_once_with("dumpdata", "auth.group", "evaluation", "rewards", "grades", indent=2, output=outfile_name)


@override_settings(REMIND_X_DAYS_AHEAD_OF_END_DATE=[0, 2])
class TestSendRemindersCommand(TestCase):
    today = datetime.date.today()

    def test_remind_user_about_one_course(self):
        user_to_remind = mommy.make(UserProfile)
        course = mommy.make(
                Course,
                state='in_evaluation',
                vote_start_date=self.today - datetime.timedelta(days=1),
                vote_end_date=self.today + datetime.timedelta(days=2),
                participants=[user_to_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEqual(mock.call_count, 1)
        mock.assert_called_once_with(user_to_remind, first_due_in_days=2, due_courses=[(course, 2)])

    def test_remind_user_once_about_two_courses(self):
        user_to_remind = mommy.make(UserProfile)
        course1 = mommy.make(
                Course,
                state='in_evaluation',
                vote_start_date=self.today - datetime.timedelta(days=1),
                vote_end_date=self.today + datetime.timedelta(days=0),
                participants=[user_to_remind])
        course2 = mommy.make(
                Course,
                state='in_evaluation',
                vote_start_date=self.today - datetime.timedelta(days=1),
                vote_end_date=self.today + datetime.timedelta(days=2),
                participants=[user_to_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEqual(mock.call_count, 1)
        mock.assert_called_once_with(user_to_remind, first_due_in_days=0, due_courses=[(course1, 0), (course2, 2)])

    def test_dont_remind_already_voted(self):
        user_no_remind = mommy.make(UserProfile)
        mommy.make(
                Course,
                state='in_evaluation',
                vote_start_date=self.today - datetime.timedelta(days=1),
                vote_end_date=self.today + datetime.timedelta(days=2),
                participants=[user_no_remind],
                voters=[user_no_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEqual(mock.call_count, 0)
        self.assertEqual(len(mail.outbox), 0)
