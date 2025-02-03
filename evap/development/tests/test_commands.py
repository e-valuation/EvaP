from io import StringIO
from unittest.mock import call, patch

from django.conf import settings
from django.core import management

from evap.evaluation.tests.tools import TestCase


class TestDumpTestDataCommand(TestCase):
    @staticmethod
    def test_dumpdata_called():
        with patch("evap.evaluation.management.commands.tools.call_command") as mock:
            management.call_command("dump_testdata", stdout=StringIO())

        outfile_name = settings.MODULE / "development" / "fixtures" / "test_data.json"
        mock.assert_called_once_with(
            "dumpdata",
            "auth.group",
            "evaluation",
            "rewards",
            "student",
            "grades",
            "--exclude=evaluation.LogEntry",
            indent=2,
            natural_foreign=True,
            natural_primary=True,
            output=outfile_name,
        )


class TestReloadTestdataCommand(TestCase):
    @patch("builtins.input", return_value="not yes")
    @patch("evap.development.management.commands.reload_testdata.shutil")
    @patch("evap.evaluation.management.commands.tools.call_command")
    def test_aborts(self, mock_call_command, mock_shutil, _mock_input):
        management.call_command("reload_testdata", stdout=StringIO())

        self.assertEqual(mock_call_command.call_count, 0)
        self.assertFalse(mock_shutil.method_calls)

    @patch("builtins.input", return_value="yes")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("evap.development.management.commands.reload_testdata.shutil")
    @patch("evap.evaluation.management.commands.tools.call_command")
    def test_executes_key_commands(self, mock_call_command, mock_shutil, mock_exists, _mock_input):
        management.call_command("reload_testdata", stdout=StringIO())

        mock_call_command.assert_any_call("reset_db", interactive=False)
        mock_call_command.assert_any_call("migrate")
        mock_call_command.assert_any_call("flush", interactive=False)
        mock_call_command.assert_any_call("loaddata", "test_data")
        mock_call_command.assert_any_call("clear_cache", "--all", "-v=1")
        mock_call_command.assert_any_call("refresh_results_cache")

        self.assertEqual(mock_call_command.call_count, 6)

        # The directory for uploads is cleared and reinitialized
        mock_exists.assert_called_once()
        mock_shutil.rmtree.assert_called_once()
        mock_shutil.copytree.assert_called_once()


class TestRunCommand(TestCase):
    def test_calls_runserver(self):
        with patch("django.core.management.execute_from_command_line") as execute_mock:
            with patch("subprocess.Popen") as popen_mock:
                management.call_command("run", stdout=StringIO())

        execute_mock.assert_called_once_with(["manage.py", "runserver", "0.0.0.0:8000"])
        self.assertEqual(popen_mock.call_count, 2)
        popen_mock.assert_has_calls(
            [
                call(["./manage.py", "scss"]),
                call(["./manage.py", "ts", "compile"]),
            ],
            any_order=True,
        )
