import os
from datetime import date
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError, call_command
from model_bakery import baker

from evap.evaluation.models import Semester
from evap.evaluation.tests.tools import TestCase


class TestImportCMSData(TestCase):
    @patch("requests.get")
    @patch("evap.cms.management.commands.import_cms_data.JSONImporter")
    def test_download_import(self, mock_json_importer, mock_get):
        semester = baker.make(Semester, cms_name="WS 25/26", default_course_end_date=date(2026, 2, 28))
        baker.make(Semester, cms_name="WS 2025")
        baker.make(Semester, default_course_end_date=date(2026, 2, 28))

        url_template = "https://example.com/download?semester={}"
        call_command("import_cms_data", "download", url_template, stdout=StringIO())

        mock_get.assert_called_once_with("https://example.com/download?semester=WS%2025/26", timeout=120)
        mock_json_importer.assert_called_once_with(semester, semester.default_course_end_date)

    @patch("evap.cms.management.commands.import_cms_data.JSONImporter.import_json")
    def test_file_import(self, mock_import_json):
        semester = baker.make(Semester)
        with TemporaryDirectory() as temp_dir:
            test_filename = os.path.join(temp_dir, "test.json")
            with open(test_filename, "w", encoding="utf-8") as f:
                f.write("example contents")
            call_command(
                "import_cms_data",
                "file",
                "--semester-id",
                semester.id,
                "--default-course-end-date",
                "2000-01-01",
                test_filename,
                stdout=StringIO(),
            )

            mock_import_json.assert_called_once_with("example contents")

            with self.assertRaises(CommandError) as cm:
                call_command(
                    "import_cms_data",
                    "file",
                    "--semester-id",
                    semester.id + 42,
                    "--default-course-end-date",
                    "2000-01-01",
                    test_filename,
                    stdout=StringIO(),
                )
            self.assertEqual(cm.exception.args, ("Semester does not exist.",))

    @patch("evap.cms.management.commands.import_cms_data.JSONImporter")
    def test_uses_semester_default_course_end_date(self, mock_json_importer):
        semester = baker.make(Semester, default_course_end_date=date(2001, 2, 3))
        with TemporaryDirectory() as temp_dir:
            test_filename = os.path.join(temp_dir, "test.json")
            with open(test_filename, "w", encoding="utf-8") as f:
                f.write("example contents")
            call_command(
                "import_cms_data",
                "file",
                "--semester-id",
                semester.id,
                test_filename,
                stdout=StringIO(),
            )

            mock_json_importer.assert_called_once_with(semester, date(2001, 2, 3))
