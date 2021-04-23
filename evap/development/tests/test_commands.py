from io import StringIO
import os
from unittest.mock import patch, call

from django.core import management
from django.conf import settings
from django.test import TestCase


class TestDumpTestDataCommand(TestCase):
    @staticmethod
    def test_dumpdata_called():
        with patch('evap.development.management.commands.dump_testdata.call_command') as mock:
            management.call_command('dump_testdata')

        outfile_name = os.path.join(settings.BASE_DIR, 'development', 'fixtures', 'test_data.json')
        mock.assert_called_once_with('dumpdata', 'auth.group', 'evaluation', 'rewards', 'student', 'grades',
                                     '--exclude=evaluation.LogEntry', indent=2, natural_foreign=True,
                                     natural_primary=True, output=outfile_name)


class TestReloadTestdataCommand(TestCase):
    @patch('builtins.input')
    @patch('evap.development.management.commands.reload_testdata.call_command')
    def test_aborts(self, mock_call_command, mock_input):
        mock_input.return_value = 'not yes'

        management.call_command('reload_testdata', stdout=StringIO())

        self.assertEqual(mock_call_command.call_count, 0)

    @patch('builtins.input')
    @patch('evap.development.management.commands.reload_testdata.call_command')
    def test_executes_key_commands(self, mock_call_command, mock_input):
        mock_input.return_value = 'yes'

        management.call_command('reload_testdata', stdout=StringIO())

        mock_call_command.assert_any_call('reset_db', interactive=False)
        mock_call_command.assert_any_call('migrate')
        mock_call_command.assert_any_call('flush', interactive=False)
        mock_call_command.assert_any_call('loaddata', 'test_data')
        mock_call_command.assert_any_call('clear_cache')
        mock_call_command.assert_any_call('refresh_results_cache')
        mock_call_command.assert_any_call('clear_cache', '--cache=sessions')

        self.assertEqual(mock_call_command.call_count, 7)


class TestRunCommand(TestCase):
    @staticmethod
    def test_calls_runserver():
        with patch('django.core.management.execute_from_command_line') as mock:
            management.call_command('run', stdout=StringIO())

        mock.assert_has_calls([
            call(['manage.py', 'scss']),
            call(['manage.py', 'runserver', '0.0.0.0:8000']),
        ])
