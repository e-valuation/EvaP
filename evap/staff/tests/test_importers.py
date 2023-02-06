from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import TestCase, override_settings
from model_bakery import baker

import evap.staff.fixtures.excel_files_test_data as excel_data
from evap.evaluation.models import Contribution, Course, CourseType, Degree, Evaluation, Semester, UserProfile
from evap.staff.importers import (
    ImporterLog,
    ImporterLogEntry,
    import_enrollments,
    import_persons_from_evaluation,
    import_users,
)
from evap.staff.importers.base import ExcelFileLocation, ExcelFileRowMapper, InputRow
from evap.staff.tools import ImportType, user_edit_link


class TestExcelFileRowMapper(TestCase):
    @dataclass
    class SingleColumnInputRow(InputRow):
        column_count = 1
        location: ExcelFileLocation
        value: str

    def test_skip_first_n_rows_handled_correctly(self):
        workbook_data = {"SheetName": [[str(i)] for i in range(10)]}
        workbook_file_contents = excel_data.create_memory_excel_file(workbook_data)

        mapper = ExcelFileRowMapper(skip_first_n_rows=3, row_cls=self.SingleColumnInputRow, importer_log=ImporterLog())
        rows = mapper.map(workbook_file_contents)

        self.assertEqual(rows[0].location, ExcelFileLocation("SheetName", 3))
        self.assertEqual(rows[0].value, "3")


class TestUserImport(TestCase):
    # valid user import tested in tests/test_views.py, TestUserImportView

    @classmethod
    def setUpTestData(cls):
        cls.valid_excel_file_content = excel_data.create_memory_excel_file(excel_data.valid_user_import_filedata)
        cls.missing_values_excel_file_content = excel_data.create_memory_excel_file(
            excel_data.missing_values_user_import_filedata
        )
        cls.random_excel_file_content = excel_data.random_file_content

        cls.duplicate_excel_content = excel_data.create_memory_excel_file(excel_data.duplicate_user_import_filedata)
        cls.mismatching_excel_content = excel_data.create_memory_excel_file(excel_data.mismatching_user_import_filedata)
        cls.numerical_excel_content = excel_data.create_memory_excel_file(
            excel_data.numerical_data_in_user_data_filedata
        )

        cls.wrong_column_count_excel_content = excel_data.create_memory_excel_file(
            excel_data.wrong_column_count_excel_data
        )

    def test_test_run_does_not_change_database(self):
        original_users = list(UserProfile.objects.all())
        import_users(self.valid_excel_file_content, test_run=True)
        self.assertEqual(original_users, list(UserProfile.objects.all()))

    def test_test_and_notest_equality(self):
        list_test, importer_log_test = import_users(self.valid_excel_file_content, test_run=True)
        list_notest, importer_log_notest = import_users(self.valid_excel_file_content, test_run=False)

        notest_string_list = [f"{user.full_name} {user.email}" for user in list_notest]
        test_string_list = [f"{user.full_name} {user.email}" for user in list_test]

        self.assertEqual(notest_string_list, test_string_list)

        # success messages are supposed to be different in a test and import run
        self.assertEqual(importer_log_test.warnings_by_category(), importer_log_notest.warnings_by_category())
        self.assertEqual(importer_log_test.errors_by_category(), importer_log_notest.errors_by_category())

    def test_created_users(self):
        original_user_count = UserProfile.objects.count()

        user_list, importer_log = import_users(self.valid_excel_file_content, test_run=False)

        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("Successfully read sheet 'Users'.", success_messages)
        self.assertIn(
            "Successfully created 2 users:<br />Lucilia Manilium (lucilia.manilium@institution.example.com)<br />Bastius Quid (bastius.quid@external.example.com)",
            success_messages,
        )
        self.assertIn("Successfully read Excel file.", success_messages)
        self.assertEqual(importer_log.warnings_by_category(), {})
        self.assertEqual(importer_log.errors_by_category(), {})

        self.assertEqual(len(user_list), 2)
        self.assertEqual(UserProfile.objects.count(), 2 + original_user_count)
        self.assertTrue(isinstance(user_list[0], UserProfile))
        self.assertTrue(UserProfile.objects.filter(email="lucilia.manilium@institution.example.com").exists())
        self.assertTrue(UserProfile.objects.filter(email="bastius.quid@external.example.com").exists())

    @patch("evap.staff.importers.user.clean_email", new=(lambda email: "cleaned_" + email))
    def test_emails_are_cleaned(self):
        original_user_count = UserProfile.objects.count()
        __, __ = import_users(self.valid_excel_file_content, test_run=False)
        self.assertEqual(UserProfile.objects.count(), 2 + original_user_count)
        self.assertTrue(UserProfile.objects.filter(email="cleaned_lucilia.manilium@institution.example.com").exists())
        self.assertTrue(UserProfile.objects.filter(email="cleaned_bastius.quid@external.example.com").exists())

    def test_duplicate_warning(self):
        user = baker.make(UserProfile, first_name="Lucilia", last_name="Manilium", email="luma@institution.example.com")

        __, importer_log_test = import_users(self.valid_excel_file_content, test_run=True)
        __, importer_log_notest = import_users(self.valid_excel_file_content, test_run=False)

        self.assertEqual(importer_log_test.warnings_by_category(), importer_log_notest.warnings_by_category())
        self.assertEqual(
            [msg.message for msg in importer_log_test.warnings_by_category()[ImporterLogEntry.Category.DUPL]],
            [
                "A user in the import file has the same first and last name as an existing user:<br />"
                f" -  Lucilia Manilium, luma@institution.example.com [{user_edit_link(user.pk)}] (existing)<br />"
                " -  Lucilia Manilium, lucilia.manilium@institution.example.com (import)",
            ],
        )

    def test_ignored_duplicate_warning(self):
        __, importer_log_test = import_users(self.duplicate_excel_content, test_run=True)
        __, importer_log_notest = import_users(self.duplicate_excel_content, test_run=False)

        self.assertEqual(importer_log_test.errors_by_category(), {})
        self.assertEqual(importer_log_notest.errors_by_category(), {})
        self.assertEqual(importer_log_test.warnings_by_category(), importer_log_notest.warnings_by_category())
        self.assertEqual(
            [msg.message for msg in importer_log_test.warnings_by_category()[ImporterLogEntry.Category.IGNORED]],
            ['Sheet "Users", row 4: The duplicated row was ignored. It was first found at Sheet "Users", row 3.'],
        )

    def test_user_data_mismatch_in_file(self):
        __, importer_log_test = import_users(self.mismatching_excel_content, test_run=True)
        __, importer_log_notest = import_users(self.mismatching_excel_content, test_run=False)

        self.assertEqual(importer_log_test.warnings_by_category(), {})
        self.assertEqual(importer_log_notest.warnings_by_category(), {})
        self.assertEqual(importer_log_test.errors_by_category(), importer_log_notest.errors_by_category())
        self.assertEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.USER]],
            [
                'Sheet "Users", row 4: The users\'s data (email: bastius.quid@external.example.com) is different to a previous row.'
            ],
        )

    def test_user_data_mismatch_to_database(self):
        user_basti = baker.make(
            UserProfile, first_name="Basti", last_name="Quid", email="bastius.quid@external.example.com"
        )

        __, importer_log = import_users(self.valid_excel_file_content, test_run=True)
        self.assertEqual(
            [
                "The existing user would be overwritten with the following data:<br />"
                f" -  Basti Quid, bastius.quid@external.example.com [{user_edit_link(user_basti.pk)}] (existing)<br />"
                " -  Bastius Quid, bastius.quid@external.example.com (import)",
            ],
            [msg.message for msg in importer_log.warnings_by_category()[ImporterLogEntry.Category.NAME]],
        )

        __, importer_log = import_users(self.valid_excel_file_content, test_run=False)
        self.assertEqual(
            [
                "The existing user was overwritten with the following data:<br />"
                f" -  Basti Quid, bastius.quid@external.example.com [{user_edit_link(user_basti.pk)}] (existing)<br />"
                " -  Bastius Quid, bastius.quid@external.example.com (import)"
            ],
            [msg.message for msg in importer_log.warnings_by_category()[ImporterLogEntry.Category.NAME]],
        )

    def test_random_file_error(self):
        original_user_count = UserProfile.objects.count()

        __, importer_log_test = import_users(self.random_excel_file_content, test_run=True)
        __, importer_log_notest = import_users(self.random_excel_file_content, test_run=False)

        self.assertEqual(importer_log_test.errors_by_category(), importer_log_notest.errors_by_category())
        self.assertEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.SCHEMA]],
            ["Couldn't read the file. Error: File is not a zip file"],
        )
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_missing_values_error(self):
        original_user_count = UserProfile.objects.count()

        __, importer_log_test = import_users(self.missing_values_excel_file_content, test_run=True)
        __, importer_log_notest = import_users(self.missing_values_excel_file_content, test_run=False)

        self.assertEqual(importer_log_test.errors_by_category(), importer_log_notest.errors_by_category())
        self.assertEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.USER]],
            [
                'Sheet "Sheet 1", row 2: User missing.firstname@institution.example.com: First name is missing.',
                'Sheet "Sheet 1", row 3: User missing.lastname@institution.example.com: Last name is missing.',
                'Sheet "Sheet 1", row 4: Email address is missing.',
            ],
        )
        self.assertEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.RESULT]],
            ["Errors occurred while parsing the input data. No data was imported."],
        )
        self.assertEqual(len(importer_log_test.errors_by_category()), 2)
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_import_makes_inactive_user_active(self):
        user = baker.make(UserProfile, email="lucilia.manilium@institution.example.com", is_active=False)

        __, importer_log_test = import_users(self.valid_excel_file_content, test_run=True)
        self.assertEqual(
            [msg.message for msg in importer_log_test.warnings_by_category()[ImporterLogEntry.Category.INACTIVE]],
            [
                "The following user is currently marked inactive and will be marked active upon importing: "
                f" None None, lucilia.manilium@institution.example.com [{user_edit_link(user.pk)}]",
            ],
        )

        __, importer_log_notest = import_users(self.valid_excel_file_content, test_run=False)
        self.assertEqual(
            [msg.message for msg in importer_log_notest.warnings_by_category()[ImporterLogEntry.Category.INACTIVE]],
            [
                "The following user was previously marked inactive and is now marked active upon importing: "
                f" None None, lucilia.manilium@institution.example.com [{user_edit_link(user.pk)}]"
            ],
        )

        self.assertEqual(UserProfile.objects.count(), 2)

    @patch("evap.evaluation.models.UserProfile.full_clean")
    def test_validation_error(self, mocked_validation):
        mocked_validation.side_effect = [None, ValidationError("TEST")]

        original_user_count = UserProfile.objects.count()
        user_list, importer_log = import_users(self.valid_excel_file_content, test_run=False)
        self.assertEqual(UserProfile.objects.count(), original_user_count)

        self.assertEqual(user_list, [])
        self.assertEqual(
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.USER]],
            [
                "User bastius.quid@external.example.com: Error when validating: ['TEST']",
            ],
        )

    @override_settings(DEBUG=False)
    @patch("evap.evaluation.models.UserProfile.save")
    def test_unhandled_exception(self, mocked_db_access):
        mocked_db_access.side_effect = Exception("Contact your database admin right now!")
        result, importer_log = import_users(self.valid_excel_file_content, test_run=False)
        self.assertEqual(result, [])
        self.assertIn(
            "Import aborted after exception: 'Contact your database admin right now!'. No data was imported.",
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.GENERAL]],
        )

    def test_disallow_non_string_types(self):
        imported_users, importer_log = import_users(self.numerical_excel_content, test_run=False)
        self.assertEqual(len(imported_users), 0)
        self.assertEqual(
            ["Errors occurred while parsing the input data. No data was imported."],
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.RESULT]],
        )
        # The sheet has a float in row 3 and an int row 4. All others rows only contain strings.
        self.assertCountEqual(
            [
                'Sheet "Users", row 3: Wrong data type. Please make sure all cells are string types, not numerical.',
                'Sheet "Users", row 4: Wrong data type. Please make sure all cells are string types, not numerical.',
            ],
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.SCHEMA]],
        )

    def test_wrong_column_count(self):
        imported_users, importer_log = import_users(self.wrong_column_count_excel_content, test_run=False)
        self.assertEqual(len(imported_users), 0)
        self.assertEqual(
            ["Errors occurred while parsing the input data. No data was imported."],
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.RESULT]],
        )
        self.assertEqual(
            ["Wrong number of columns in sheet 'Sheet 1'. Expected: 4, actual: 3"],
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.GENERAL]],
        )


class TestEnrollmentImport(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.random_excel_file_content = excel_data.random_file_content

        cls.semester = baker.make(Semester)
        cls.vote_start_datetime = datetime(2017, 1, 10)
        cls.vote_end_date = date(2017, 3, 10)
        baker.make(CourseType, name_de="Seminar", import_names=["Seminar", "S"])
        baker.make(CourseType, name_de="Vorlesung", import_names=["Vorlesung", "V"])
        Degree.objects.filter(name_de="Bachelor").update(import_names=["Bachelor", "B. Sc."])
        Degree.objects.filter(name_de="Master").update(import_names=["Master", "M. Sc."])
        cls.default_excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata)
        cls.empty_excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_empty_filedata)

    def create_existing_course(self):
        existing_course = baker.make(
            Course,
            name_de="Schütteln",
            name_en="Shake",
            semester=self.semester,
            type=CourseType.objects.get(name_de="Vorlesung"),
            degrees=[Degree.objects.get(name_de="Bachelor")],
            responsibles=[
                baker.make(
                    UserProfile,
                    email="123@institution.example.com",
                    title="Prof. Dr.",
                    first_name="Christoph",
                    last_name="Prorsus",
                )
            ],
        )
        existing_course_evaluation = baker.make(Evaluation, course=existing_course)
        return existing_course, existing_course_evaluation

    def test_valid_file_import(self):
        importer_log = import_enrollments(self.default_excel_content, self.semester, None, None, test_run=True)

        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("The import run will create 23 courses/evaluations and 23 users:", "".join(success_messages))
        # check for one random user instead of for all 23
        self.assertIn("Ferdi Itaque (789@institution.example.com)", "".join(success_messages))
        self.assertEqual(importer_log.errors_by_category(), {})
        self.assertEqual(importer_log.warnings_by_category(), {})

        old_user_count = UserProfile.objects.all().count()

        importer_log = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn(
            "Successfully created 23 courses/evaluations, 6 participants and 17 contributors:",
            "".join(success_messages),
        )
        self.assertIn("Ferdi Itaque (789@institution.example.com)", "".join(success_messages))
        self.assertEqual(importer_log.errors_by_category(), {})
        self.assertEqual(importer_log.warnings_by_category(), {})

        self.assertEqual(Evaluation.objects.all().count(), 23)
        expected_user_count = old_user_count + 23
        self.assertEqual(UserProfile.objects.all().count(), expected_user_count)

    @patch("evap.staff.importers.user.clean_email", new=(lambda email: "cleaned_" + email))
    @patch("evap.staff.importers.enrollment.clean_email", new=(lambda email: "cleaned_" + email))
    def test_emails_are_cleaned(self):
        import_enrollments(self.default_excel_content, self.semester, None, None, test_run=True)

        old_user_count = UserProfile.objects.all().count()

        import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )
        expected_user_count = old_user_count + 23
        self.assertEqual(UserProfile.objects.all().count(), expected_user_count)

        self.assertTrue(UserProfile.objects.filter(email="cleaned_bastius.quid@external.example.com").exists())
        self.assertTrue(UserProfile.objects.filter(email="cleaned_diam.synephebos@institution.example.com").exists())
        self.assertTrue(UserProfile.objects.filter(email="cleaned_111@institution.example.com").exists())

    def test_import_with_empty_excel(self):
        importer_log = import_enrollments(self.empty_excel_content, self.semester, None, None, test_run=True)

        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("The import run will create 0 courses/evaluations and 0 users.", success_messages)

        importer_log = import_enrollments(
            self.empty_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn(
            "Successfully created 0 courses/evaluations, 0 participants and 0 contributors.",
            success_messages,
        )

    def test_degrees_are_merged(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_degree_merge_filedata)

        importer_log_test = import_enrollments(excel_content, self.semester, None, None, test_run=True)
        success_messages_test = [msg.message for msg in importer_log_test.success_messages()]
        self.assertIn("The import run will create 1 course/evaluation and 3 users", "".join(success_messages_test))
        self.assertEqual(importer_log_test.errors_by_category(), {})
        self.assertEqual(
            [msg.message for msg in importer_log_test.warnings_by_category()[ImporterLogEntry.Category.DEGREE]],
            [
                'Sheet "MA Belegungen", row 3: The degree of course "Build" differs from its degrees in previous rows. '
                "All degrees have been set for the course."
            ],
        )
        self.assertEqual(len(importer_log_test.warnings_by_category()), 1)

        importer_log_notest = import_enrollments(
            excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )
        success_messages_notest = [msg.message for msg in importer_log_notest.success_messages()]
        self.assertIn(
            "Successfully created 1 course/evaluation, 2 participants and 1 contributor",
            "".join(success_messages_notest),
        )
        self.assertEqual(importer_log_test.errors_by_category(), {})
        self.assertEqual(importer_log_test.warnings_by_category(), importer_log_test.warnings_by_category())

        self.assertEqual(Course.objects.all().count(), 1)
        self.assertEqual(Evaluation.objects.all().count(), 1)

        course = Course.objects.get(name_de="Bauen")
        self.assertSetEqual(set(course.degrees.all()), set(Degree.objects.filter(name_de__in=["Master", "Bachelor"])))

    def test_errors_are_merged(self):
        """Whitebox regression test for #1711. Importers were rewritten afterwards, so this test has limited meaning now."""
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_error_merge_filedata)
        importer_log = import_enrollments(
            excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )

        errors = [entry.message for entry in importer_log.messages if entry.level == ImporterLogEntry.Level.ERROR]

        self.assertCountEqual(
            errors,
            [
                'Sheet "MA Belegungen", row 2 and 1 other place: No course type is associated with the import name "jaminar". Please manually create it first.',
                'Sheet "MA Belegungen", row 2 and 1 other place: "is_graded" is probably not, but must be yes or no',
                'Sheet "MA Belegungen", row 2: No degree is associated with the import name "Grandmaster". Please manually create it first.',
                'Sheet "MA Belegungen", row 3: No degree is associated with the import name "Beginner". Please manually create it first.',
                "Errors occurred while parsing the input data. No data was imported.",
            ],
        )

    def test_course_type_and_degrees_are_retrieved_with_import_names(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_import_names_filedata)

        importer_log = import_enrollments(
            excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn(
            "Successfully created 2 courses/evaluations, 4 participants and 2 contributors:", "".join(success_messages)
        )
        self.assertEqual(importer_log.errors_by_category(), {})
        self.assertEqual(importer_log.warnings_by_category(), {})

        self.assertEqual(Course.objects.all().count(), 2)
        course_spelling = Course.objects.get(name_en="Spelling")
        self.assertEqual(course_spelling.type.name_de, "Vorlesung")
        self.assertEqual(list(course_spelling.degrees.values_list("name_en", flat=True)), ["Bachelor"])
        course_build = Course.objects.get(name_en="Build")
        self.assertEqual(course_build.type.name_de, "Seminar")
        self.assertEqual(list(course_build.degrees.values_list("name_en", flat=True)), ["Master"])

    @override_settings(IMPORTER_MAX_ENROLLMENTS=1)
    def test_enrollment_importer_high_enrollment_warning(self):
        importer_log_test = import_enrollments(self.default_excel_content, self.semester, None, None, test_run=True)
        importer_log_notest = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )

        self.assertEqual(importer_log_test.warnings_by_category(), importer_log_notest.warnings_by_category())
        self.assertCountEqual(
            [
                msg.message
                for msg in importer_log_test.warnings_by_category()[ImporterLogEntry.Category.TOO_MANY_ENROLLMENTS]
            ],
            {
                "Warning: User ipsum.lorem@institution.example.com has 6 enrollments, which is a lot.",
                "Warning: User lucilia.manilium@institution.example.com has 6 enrollments, which is a lot.",
                "Warning: User diam.synephebos@institution.example.com has 6 enrollments, which is a lot.",
                "Warning: User torquate.metrodorus@institution.example.com has 6 enrollments, which is a lot.",
                "Warning: User latinas.menandri@institution.example.com has 5 enrollments, which is a lot.",
                "Warning: User bastius.quid@external.example.com has 4 enrollments, which is a lot.",
            },
        )

    def test_random_file_error(self):
        original_user_count = UserProfile.objects.count()

        importer_log_test = import_enrollments(self.random_excel_file_content, self.semester, None, None, test_run=True)
        importer_log_notest = import_enrollments(
            self.random_excel_file_content, self.semester, None, None, test_run=False
        )

        self.assertEqual(importer_log_test.errors_by_category(), importer_log_notest.errors_by_category())
        self.assertEqual(1, len(importer_log_test.errors_by_category()[ImporterLogEntry.Category.SCHEMA]))
        self.assertEqual(
            importer_log_test.errors_by_category()[ImporterLogEntry.Category.SCHEMA][0].message,
            "Couldn't read the file. Error: File is not a zip file",
        )
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_invalid_file_error(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.invalid_enrollment_data_filedata)

        original_user_count = UserProfile.objects.count()

        importer_log_test = import_enrollments(excel_content, self.semester, None, None, test_run=True)
        importer_log_notest = import_enrollments(excel_content, self.semester, None, None, test_run=False)

        self.assertEqual(importer_log_test.errors_by_category(), importer_log_notest.errors_by_category())
        self.assertCountEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.USER]],
            [
                'Sheet "MA Belegungen", row 3: The users\'s data (email: bastius.quid@external.example.com) is different to a previous row.',
                'Sheet "MA Belegungen", row 7: Email address is missing.',
                'Sheet "MA Belegungen", row 10: Email address is missing.',
            ],
        )
        self.assertCountEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.COURSE]],
            [
                'Sheet "MA Belegungen", row 18: The German name for course "Bought" is already used for another course in the import file.',
                'Sheet "MA Belegungen", row 20: The data of course "Cost" differs from its data in the columns (responsible_email) in a previous row.',
            ],
        )
        self.assertEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.DEGREE_MISSING]],
            [
                'Sheet "MA Belegungen", row 8 and 1 other place: No degree is associated with the import name "Diploma". Please manually create it first.'
            ],
        )
        self.assertEqual(
            [
                msg.message
                for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.COURSE_TYPE_MISSING]
            ],
            [
                'Sheet "MA Belegungen", row 11 and 1 other place: No course type is associated with the import name "Praktikum". Please manually create it first.'
            ],
        )
        self.assertEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.IS_GRADED]],
            ['Sheet "MA Belegungen", row 5: "is_graded" is maybe, but must be yes or no'],
        )
        self.assertEqual(
            [msg.message for msg in importer_log_test.errors_by_category()[ImporterLogEntry.Category.RESULT]],
            ["Errors occurred while parsing the input data. No data was imported."],
        )
        self.assertEqual(len(importer_log_test.errors_by_category()), 6)
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_duplicate_course_error(self):
        semester = baker.make(Semester)
        baker.make(Course, name_de="Scheinen2", name_en="Shine", semester=semester)
        baker.make(Course, name_de="Stehlen", name_en="Steal2", semester=semester)

        importer_log = import_enrollments(self.default_excel_content, semester, None, None, test_run=False)
        self.assertCountEqual(
            [
                'Sheet "BA Belegungen", row 8: Course "Shine" (EN) already exists in this semester with a different german name.',
                'Sheet "BA Belegungen", row 10: Course "Stehlen" (DE) already exists in this semester with a different english name.',
            ],
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.COURSE]],
        )

    def test_unknown_degree_error(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_unknown_degree_error_filedata)
        importer_log = import_enrollments(excel_content, baker.make(Semester), None, None, test_run=False)
        missing_degree_errors = importer_log.errors_by_category()[ImporterLogEntry.Category.DEGREE_MISSING]
        self.assertEqual(len(missing_degree_errors), 1)
        self.assertIn("manually create it first", missing_degree_errors[0].message)

    @patch("evap.evaluation.models.UserProfile.full_clean")
    def test_validation_error(self, mocked_validation):
        mocked_validation.side_effect = [None] * 5 + [ValidationError("TEST")] + [None] * 50

        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata)
        importer_log = import_enrollments(excel_content, self.semester, None, None, test_run=False)

        self.assertEqual(
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.USER]],
            [
                "User diam.synephebos@institution.example.com: Error when validating: ['TEST']",
            ],
        )

    def test_replace_consecutive_and_trailing_spaces(self):
        excel_content = excel_data.create_memory_excel_file(
            excel_data.test_enrollment_data_consecutive_and_trailing_spaces_filedata
        )

        importer_log = import_enrollments(excel_content, self.semester, None, None, test_run=True)
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("The import run will create 1 course/evaluation and 3 users", "".join(success_messages))

    def test_existing_course_is_not_recreated(self):
        existing_course, existing_course_evaluation = self.create_existing_course()

        old_course_count = Course.objects.count()
        old_dict = model_to_dict(existing_course)
        self.assertFalse(existing_course_evaluation.participants.exists())

        importer_log_test = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=True
        )
        importer_log_notest = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )

        warnings_test = [
            msg.message for msg in importer_log_test.warnings_by_category()[ImporterLogEntry.Category.EXISTS]
        ]

        warnings_notest = [
            msg.message for msg in importer_log_notest.warnings_by_category()[ImporterLogEntry.Category.EXISTS]
        ]

        self.assertIn(
            'Course "Shake" already exists. The course will not be created, instead users are imported into the '
            + "evaluation of the existing course and any additional degrees are added.",
            warnings_test,
        )
        self.assertListEqual(warnings_test, warnings_notest)

        success_messages_test_joined = "".join(msg.message for msg in importer_log_test.success_messages())
        self.assertIn("The import run will create 22 courses/evaluations", success_messages_test_joined)

        success_messages_notest_joined = "".join(msg.message for msg in importer_log_notest.success_messages())
        self.assertIn("Successfully created 22 courses/evaluations", success_messages_notest_joined)

        expected_course_count = old_course_count + 22
        self.assertEqual(Course.objects.count(), expected_course_count)
        existing_course.refresh_from_db()
        self.assertEqual(old_dict, model_to_dict(existing_course))
        self.assertIn(
            UserProfile.objects.get(email="lucilia.manilium@institution.example.com"),
            existing_course_evaluation.participants.all(),
        )

    def test_existing_course_degree_is_added(self):
        existing_course, __ = self.create_existing_course()

        # The existing course exactly matches one course in the import data by default. To create a conflict, the degrees are changed
        existing_course.degrees.set([Degree.objects.get(name_de="Master")])

        import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )

        self.assertSetEqual(
            set(existing_course.degrees.all()), set(Degree.objects.filter(name_de__in=["Master", "Bachelor"]))
        )

    def test_existing_course_different_attributes(self):
        existing_course, __ = self.create_existing_course()
        existing_course.type = CourseType.objects.get(name_de="Seminar")
        existing_course.responsibles.set([baker.make(UserProfile, email="responsible_person@institution.example.com")])
        existing_course.save()

        old_course_count = Course.objects.count()
        old_dict = model_to_dict(existing_course)

        importer_log = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )

        self.assertIn(
            "Sheet &quot;BA Belegungen&quot;, row 2 and 1 other place: Course &quot;Shake&quot; already exists in this "
            + "semester, but the courses can not be merged for the following reasons:"
            + "<br /> - the course type does not match"
            + "<br /> - the responsibles of the course do not match",
            [entry.message for entry in importer_log.errors_by_category()[ImporterLogEntry.Category.COURSE]],
        )

        self.assertEqual(Course.objects.count(), old_course_count)
        existing_course.refresh_from_db()
        self.assertEqual(old_dict, model_to_dict(existing_course))

    def test_existing_course_equal_except_evaluations(self):
        existing_course, __ = self.create_existing_course()
        baker.make(Evaluation, course=existing_course, name_de="Zweite Evaluation", name_en="Second Evaluation")

        old_course_count = Course.objects.count()
        old_dict = model_to_dict(existing_course)

        importer_log = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )

        self.assertIn(
            "Sheet &quot;BA Belegungen&quot;, row 2 and 1 other place: Course &quot;Shake&quot; already exists in "
            + "this semester, but the courses can not be merged for the following reasons:"
            + "<br /> - the existing course does not have exactly one evaluation",
            [entry.message for entry in importer_log.errors_by_category()[ImporterLogEntry.Category.COURSE]],
        )
        self.assertEqual(Course.objects.count(), old_course_count)
        existing_course.refresh_from_db()
        self.assertEqual(old_dict, model_to_dict(existing_course))

    def test_existing_course_different_grading(self):
        existing_course, existing_course_evaluation = self.create_existing_course()
        existing_course_evaluation.wait_for_grade_upload_before_publishing = False
        existing_course_evaluation.save()

        old_course_count = Course.objects.count()
        old_dict = model_to_dict(existing_course)

        importer_log = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )

        self.assertIn(
            "Sheet &quot;BA Belegungen&quot;, row 2 and 1 other place: Course &quot;Shake&quot; already exists in this "
            + "semester, but the courses can not be merged for the following reasons:"
            + "<br /> - the evaluation of the existing course has a mismatching grading specification",
            [entry.message for entry in importer_log.errors_by_category()[ImporterLogEntry.Category.COURSE]],
        )
        self.assertEqual(Course.objects.count(), old_course_count)
        existing_course.refresh_from_db()
        self.assertEqual(old_dict, model_to_dict(existing_course))

    def test_wrong_column_count(self):
        wrong_column_count_excel_content = excel_data.create_memory_excel_file(excel_data.wrong_column_count_excel_data)
        importer_log = import_enrollments(wrong_column_count_excel_content, self.semester, None, None, test_run=True)
        self.assertEqual(
            ["Errors occurred while parsing the input data. No data was imported."],
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.RESULT]],
        )
        self.assertEqual(
            ["Wrong number of columns in sheet 'Sheet 1'. Expected: 12, actual: 3"],
            [msg.message for msg in importer_log.errors_by_category()[ImporterLogEntry.Category.GENERAL]],
        )

    def test_user_data_mismatch_to_database(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata)

        # Just check that the checker is called. It is already tested in UserImportTest.test_user_data_mismatch_to_database
        with patch("evap.staff.importers.user.UserDataMismatchChecker.check_userdata") as mock:
            import_enrollments(excel_content, self.semester, None, None, test_run=True)
            self.assertGreater(mock.call_count, 50)

    def test_duplicate_participation(self):
        input_data = deepcopy(excel_data.test_enrollment_data_filedata)
        # create a duplicate participation by duplicating a line
        input_data["MA Belegungen"].append(input_data["MA Belegungen"][1])
        excel_content = excel_data.create_memory_excel_file(input_data)

        importer_log = import_enrollments(excel_content, self.semester, None, None, test_run=True)
        self.assertEqual(importer_log.errors_by_category(), {})
        self.assertEqual(importer_log.warnings_by_category(), {})

        old_user_count = UserProfile.objects.all().count()

        importer_log = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )
        self.assertEqual(importer_log.errors_by_category(), {})
        self.assertEqual(importer_log.warnings_by_category(), {})

        self.assertEqual(Evaluation.objects.all().count(), 23)
        expected_user_count = old_user_count + 23
        self.assertEqual(UserProfile.objects.all().count(), expected_user_count)

    def test_existing_participation(self):
        _, existing_evaluation = self.create_existing_course()
        user = baker.make(
            UserProfile, first_name="Lucilia", last_name="Manilium", email="lucilia.manilium@institution.example.com"
        )
        existing_evaluation.participants.add(user)

        importer_log = import_enrollments(self.default_excel_content, self.semester, None, None, test_run=True)

        expected_warnings = ["Course Shake: 1 participants from the import file already participate in the evaluation."]
        self.assertEqual(
            [
                msg.message
                for msg in importer_log.warnings_by_category()[ImporterLogEntry.Category.ALREADY_PARTICIPATING]
            ],
            expected_warnings,
        )
        self.assertFalse(importer_log.has_errors())

        importer_log = import_enrollments(
            self.default_excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False
        )

        self.assertEqual(
            [
                msg.message
                for msg in importer_log.warnings_by_category()[ImporterLogEntry.Category.ALREADY_PARTICIPATING]
            ],
            expected_warnings,
        )
        self.assertFalse(importer_log.has_errors())


class TestPersonImport(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant1 = baker.make(UserProfile, email="participant1@example.com")
        cls.evaluation1 = baker.make(Evaluation, participants=[cls.participant1])
        cls.contributor1 = baker.make(UserProfile)
        cls.contribution1 = baker.make(Contribution, contributor=cls.contributor1, evaluation=cls.evaluation1)

        cls.participant2 = baker.make(UserProfile, email="participant2@example.com")
        cls.evaluation2 = baker.make(Evaluation, participants=[cls.participant2])
        cls.contributor2 = baker.make(UserProfile)
        cls.contribution2 = baker.make(Contribution, contributor=cls.contributor2, evaluation=cls.evaluation2)

    def test_import_existing_contributor(self):
        self.assertEqual(self.evaluation1.contributions.count(), 2)

        importer_log = import_persons_from_evaluation(
            ImportType.CONTRIBUTOR, self.evaluation1, test_run=True, source_evaluation=self.evaluation1
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("0 contributors would be added to the evaluation", "".join(success_messages))
        self.assertIn(
            "The following user is already contributing to evaluation",
            [msg.message for msg in importer_log.warnings_by_category()[ImporterLogEntry.Category.GENERAL]][0],
        )

        importer_log = import_persons_from_evaluation(
            ImportType.CONTRIBUTOR, self.evaluation1, test_run=False, source_evaluation=self.evaluation1
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("0 contributors added to the evaluation", "".join(success_messages))
        self.assertIn(
            "The following user is already contributing to evaluation",
            [msg.message for msg in importer_log.warnings_by_category()[ImporterLogEntry.Category.GENERAL]][0],
        )

        self.assertEqual(self.evaluation1.contributions.count(), 2)
        self.assertEqual(
            set(UserProfile.objects.filter(contributions__evaluation=self.evaluation1)), set([self.contributor1])
        )

    def test_import_new_contributor(self):
        self.assertEqual(self.evaluation1.contributions.count(), 2)

        importer_log = import_persons_from_evaluation(
            ImportType.CONTRIBUTOR, self.evaluation1, test_run=True, source_evaluation=self.evaluation2
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("1 contributor would be added to the evaluation", "".join(success_messages))
        self.assertIn(f"{self.contributor2.email}", "".join(success_messages))

        self.assertEqual(self.evaluation1.contributions.count(), 2)

        importer_log = import_persons_from_evaluation(
            ImportType.CONTRIBUTOR, self.evaluation1, test_run=False, source_evaluation=self.evaluation2
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("1 contributor added to the evaluation", "".join(success_messages))
        self.assertIn(f"{self.contributor2.email}", "".join(success_messages))

        self.assertEqual(self.evaluation1.contributions.count(), 3)
        self.assertEqual(
            set(UserProfile.objects.filter(contributions__evaluation=self.evaluation1)),
            set([self.contributor1, self.contributor2]),
        )

    def test_import_existing_participant(self):
        importer_log = import_persons_from_evaluation(
            ImportType.PARTICIPANT, self.evaluation1, test_run=True, source_evaluation=self.evaluation1
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("0 participants would be added to the evaluation", "".join(success_messages))
        self.assertIn(
            "The following user is already participating in evaluation",
            [msg.message for msg in importer_log.warnings_by_category()[ImporterLogEntry.Category.GENERAL]][0],
        )

        importer_log = import_persons_from_evaluation(
            ImportType.PARTICIPANT, self.evaluation1, test_run=False, source_evaluation=self.evaluation1
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("0 participants added to the evaluation", "".join(success_messages))
        self.assertIn(
            "The following user is already participating in evaluation",
            [msg.message for msg in importer_log.warnings_by_category()[ImporterLogEntry.Category.GENERAL]][0],
        )

        self.assertEqual(self.evaluation1.participants.count(), 1)
        self.assertEqual(self.evaluation1.participants.get(), self.participant1)

    def test_import_new_participant(self):
        importer_log = import_persons_from_evaluation(
            ImportType.PARTICIPANT, self.evaluation1, test_run=True, source_evaluation=self.evaluation2
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("1 participant would be added to the evaluation", "".join(success_messages))
        self.assertIn(f"{self.participant2.email}", "".join(success_messages))

        importer_log = import_persons_from_evaluation(
            ImportType.PARTICIPANT, self.evaluation1, test_run=False, source_evaluation=self.evaluation2
        )
        success_messages = [msg.message for msg in importer_log.success_messages()]
        self.assertIn("1 participant added to the evaluation", "".join(success_messages))
        self.assertIn(f"{self.participant2.email}", "".join(success_messages))

        self.assertEqual(self.evaluation1.participants.count(), 2)
        self.assertEqual(set(self.evaluation1.participants.all()), set([self.participant1, self.participant2]))

    def test_imported_participants_are_made_active(self):
        self.participant2.is_active = False
        self.participant2.save()

        import_persons_from_evaluation(
            ImportType.PARTICIPANT, self.evaluation1, test_run=True, source_evaluation=self.evaluation2
        )
        self.participant2.refresh_from_db()
        self.assertFalse(self.participant2.is_active)

        import_persons_from_evaluation(
            ImportType.PARTICIPANT, self.evaluation1, test_run=False, source_evaluation=self.evaluation2
        )
        self.participant2.refresh_from_db()
        self.assertTrue(self.participant2.is_active)

    def test_imported_contributors_are_made_active(self):
        self.contributor2.is_active = False
        self.contributor2.save()

        import_persons_from_evaluation(
            ImportType.CONTRIBUTOR, self.evaluation1, test_run=True, source_evaluation=self.evaluation2
        )
        self.contributor2.refresh_from_db()
        self.assertFalse(self.contributor2.is_active)

        import_persons_from_evaluation(
            ImportType.CONTRIBUTOR, self.evaluation1, test_run=False, source_evaluation=self.evaluation2
        )
        self.contributor2.refresh_from_db()
        self.assertTrue(self.contributor2.is_active)
