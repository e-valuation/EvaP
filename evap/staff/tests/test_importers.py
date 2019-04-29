import os
from collections import defaultdict
from datetime import date, datetime
from django.test import TestCase, override_settings
from django.conf import settings
from model_mommy import mommy

from evap.evaluation.models import Course, Degree, UserProfile, Semester, Evaluation, Contribution, CourseType
from evap.staff.importers import UserImporter, EnrollmentImporter, ExcelImporter, PersonImporter


class TestUserImporter(TestCase):
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls")
    filename_invalid = os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls")
    filename_random = os.path.join(settings.BASE_DIR, "staff/fixtures/random.random")

    # valid user import tested in tests/test_views.py, TestUserImportView

    @classmethod
    def setUpTestData(cls):
        with open(cls.filename_valid, "rb") as excel_file:
            cls.valid_excel_content = excel_file.read()
        with open(cls.filename_invalid, "rb") as excel_file:
            cls.invalid_excel_content = excel_file.read()
        with open(cls.filename_random, "rb") as excel_file:
            cls.random_excel_content = excel_file.read()

    def test_test_run_does_not_change_database(self):
        original_users = list(UserProfile.objects.all())
        UserImporter.process(self.valid_excel_content, test_run=True)
        self.assertEqual(original_users, list(UserProfile.objects.all()))

    def test_test_and_notest_equality(self):
        # success messages are supposed to be different in a test and import run
        list_test, __, warnings_test, errors_test = UserImporter.process(self.valid_excel_content, test_run=True)
        list_notest, __, warnings_notest, errors_notest = UserImporter.process(self.valid_excel_content, test_run=False)

        notest_string_list = ["{} {}".format(user.full_name, user.email) for user in list_notest]
        test_string_list = ["{} {}".format(user.full_name, user.email) for user in list_test]

        self.assertEqual(notest_string_list, test_string_list)
        self.assertEqual(warnings_test, warnings_notest)
        self.assertEqual(errors_test, errors_notest)

    def test_created_users(self):
        original_user_count = UserProfile.objects.count()

        user_list, success_messages, warnings, errors = UserImporter.process(self.valid_excel_content, test_run=False)

        self.assertIn("Successfully read sheet 'Users'.", success_messages)
        self.assertIn('Successfully created 2 users:<br>Lucilia Manilium (lucilia.manilium)<br>Bastius Quid (bastius.quid.ext)', success_messages)
        self.assertIn('Successfully read Excel file.', success_messages)
        self.assertEqual(warnings, {})
        self.assertEqual(errors, [])

        self.assertEqual(len(user_list), 2)
        self.assertEqual(UserProfile.objects.count(), 2 + original_user_count)
        self.assertTrue(isinstance(user_list[0], UserProfile))
        self.assertTrue(UserProfile.objects.filter(email="lucilia.manilium@institution.example.com").exists())
        self.assertTrue(UserProfile.objects.filter(email="bastius.quid@external.example.com").exists())

    def test_duplicate_warning(self):
        mommy.make(UserProfile, first_name='Lucilia', last_name="Manilium", username="lucilia.manilium2")

        __, __, warnings_test, __ = UserImporter.process(self.valid_excel_content, test_run=True)
        __, __, warnings_no_test, __ = UserImporter.process(self.valid_excel_content, test_run=False)

        self.assertEqual(warnings_test, warnings_no_test)
        self.assertIn("An existing user has the same first and last name as a new user:<br>"
                " - lucilia.manilium2 ( Lucilia Manilium, ) (existing)<br>"
                " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)",
                warnings_test[ExcelImporter.W_DUPL])

    def test_email_mismatch_warning(self):
        mommy.make(UserProfile, email="42@42.de", username="lucilia.manilium")

        __, __, warnings_test, __ = UserImporter.process(self.valid_excel_content, test_run=True)
        self.assertIn("The existing user would be overwritten with the following data:<br>"
                      " - lucilia.manilium ( None None, 42@42.de) (existing)<br>"
                      " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)",
                      warnings_test[ExcelImporter.W_EMAIL])

        __, __, warnings_no_test, __ = UserImporter.process(self.valid_excel_content, test_run=False)
        self.assertIn("The existing user was overwritten with the following data:<br>"
                " - lucilia.manilium ( None None, 42@42.de) (existing)<br>"
                " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)",
                warnings_no_test[ExcelImporter.W_EMAIL])

    def test_random_file_error(self):
        original_user_count = UserProfile.objects.count()

        __, __, __, errors_test = UserImporter.process(self.random_excel_content, test_run=True)
        __, __, __, errors_no_test = UserImporter.process(self.random_excel_content, test_run=False)

        self.assertEqual(errors_test, errors_no_test)
        self.assertIn("Couldn't read the file. Error: Unsupported format, or corrupt file:"
                " Expected BOF record; found b'42\\n'", errors_test)
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_invalid_file_error(self):
        original_user_count = UserProfile.objects.count()

        __, __, __, errors_test = UserImporter.process(self.invalid_excel_content, test_run=True)
        __, __, __, errors_no_test = UserImporter.process(self.invalid_excel_content, test_run=False)

        self.assertEqual(errors_test, errors_no_test)
        self.assertIn('Sheet "Sheet1", row 2: Email address is missing.', errors_test)
        self.assertIn('Errors occurred while parsing the input data. No data was imported.', errors_test)
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_import_makes_inactive_user_active(self):
        mommy.make(UserProfile, username="lucilia.manilium", is_active=False)

        __, __, warnings_test, __ = UserImporter.process(self.valid_excel_content, test_run=True)
        self.assertIn("The following user is currently marked inactive and will be marked active upon importing: "
                      "lucilia.manilium ( None None, )",
                      warnings_test[ExcelImporter.W_INACTIVE])

        __, __, warnings_no_test, __ = UserImporter.process(self.valid_excel_content, test_run=False)
        self.assertIn("The following user was previously marked inactive and is now marked active upon importing: "
            "lucilia.manilium ( None None, )",
            warnings_no_test[ExcelImporter.W_INACTIVE])

        self.assertEqual(UserProfile.objects.count(), 2)


class TestEnrollmentImporter(TestCase):
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/test_enrollment_data.xls")
    filename_valid_degree_merge = os.path.join(settings.BASE_DIR, "staff/fixtures/test_enrollment_data_degree_merge.xls")
    filename_invalid = os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_enrollment_data.xls")
    filename_random = os.path.join(settings.BASE_DIR, "staff/fixtures/random.random")

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester)
        cls.vote_start_datetime = datetime(2017, 1, 10)
        cls.vote_end_date = date(2017, 3, 10)
        mommy.make(CourseType, name_de="Seminar")
        mommy.make(CourseType, name_de="Vorlesung")

    def test_valid_file_import(self):
        with open(self.filename_valid, "rb") as excel_file:
            excel_content = excel_file.read()

        success_messages, warnings, errors = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        self.assertIn("The import run will create 23 courses/evaluations and 23 users:", "".join(success_messages))
        # check for one random user instead of for all 23
        self.assertIn("Ferdi Itaque (ferdi.itaque)", "".join(success_messages))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, {})

        old_user_count = UserProfile.objects.all().count()

        success_messages, warnings, errors = EnrollmentImporter.process(excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False)
        self.assertIn("Successfully created 23 courses/evaluations, 6 students and 17 contributors:", "".join(success_messages))
        self.assertIn("Ferdi Itaque (ferdi.itaque)", "".join(success_messages))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, {})

        self.assertEqual(Evaluation.objects.all().count(), 23)
        expected_user_count = old_user_count + 23
        self.assertEqual(UserProfile.objects.all().count(), expected_user_count)

    def test_degrees_are_merged(self):
        with open(self.filename_valid_degree_merge, "rb") as excel_file:
            excel_content = excel_file.read()

        expected_warnings = defaultdict(list)
        expected_warnings[EnrollmentImporter.W_DEGREE].append(
            'Sheet "MA Belegungen", row 3: The course\'s "Build" degree differs from it\'s degree in a previous row. Both degrees have been added to the course.'
        )

        success_messages, warnings, errors = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        self.assertIn("The import run will create 1 courses/evaluations and 3 users", "".join(success_messages))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, expected_warnings)

        success_messages, warnings, errors = EnrollmentImporter.process(excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False)
        self.assertIn("Successfully created 1 courses/evaluations, 2 students and 1 contributors", "".join(success_messages))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, expected_warnings)

        self.assertEqual(Course.objects.all().count(), 1)
        self.assertEqual(Evaluation.objects.all().count(), 1)

        course = Course.objects.get(name_de="Bauen")
        self.assertSetEqual(set(course.degrees.all()), set(Degree.objects.filter(name_de__in=["Master", "Bachelor"])))

    @override_settings(IMPORTER_MAX_ENROLLMENTS=1)
    def test_enrollment_importer_high_enrollment_warning(self):
        with open(self.filename_valid, "rb") as excel_file:
            excel_content = excel_file.read()

        __, warnings_test, __ = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        __, warnings_no_test, __ = EnrollmentImporter.process(excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False)

        self.assertEqual(warnings_test, warnings_no_test)
        warnings_many = warnings_test[EnrollmentImporter.W_MANY]
        self.assertIn("Warning: User ipsum.lorem has 6 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User lucilia.manilium has 6 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User diam.synephebos has 6 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User torquate.metrodorus has 6 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User latinas.menandri has 5 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User bastius.quid@external.example.com has 3 enrollments, which is a lot.", warnings_many)

    def test_random_file_error(self):
        with open(self.filename_random, "rb") as excel_file:
            excel_content = excel_file.read()

        original_user_count = UserProfile.objects.count()

        __, __, errors_test = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        __, __, errors_no_test = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=False)

        self.assertEqual(errors_test, errors_no_test)
        self.assertIn("Couldn't read the file. Error: Unsupported format, or corrupt file:"
                " Expected BOF record; found b'42\\n'", errors_test)
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_invalid_file_error(self):
        with open(self.filename_invalid, "rb") as excel_file:
            excel_content = excel_file.read()

        original_user_count = UserProfile.objects.count()

        __, __, errors_test = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        __, __, errors_no_test = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=False)

        self.assertEqual(errors_test, errors_no_test)
        self.assertIn('Sheet "MA Belegungen", row 3: The users\'s data (email: bastius.quid@external.example.com) differs from it\'s data in a previous row.', errors_test)
        self.assertIn('Sheet "MA Belegungen", row 7: Email address is missing.', errors_test)
        self.assertIn('Sheet "MA Belegungen", row 10: Email address is missing.', errors_test)
        self.assertIn('Sheet "MA Belegungen", row 18: The German name for course "Bought" already exists for another course.', errors_test)
        self.assertIn('Sheet "MA Belegungen", row 20: The course\'s "Cost" data differs from it\'s data in a previous row.', errors_test)
        self.assertIn('The imported data contains two email addresses with the same username (\'678@external.example.com\' and \'678@internal.example.com\').', errors_test)
        self.assertIn('Errors occurred while parsing the input data. No data was imported.', errors_test)
        self.assertEqual(UserProfile.objects.count(), original_user_count)


class TestPersonImporter(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant1 = mommy.make(UserProfile)
        cls.evaluation1 = mommy.make(Evaluation, participants=[cls.participant1])
        cls.contributor1 = mommy.make(UserProfile)
        cls.contribution1 = mommy.make(Contribution, contributor=cls.contributor1, evaluation=cls.evaluation1)

        cls.participant2 = mommy.make(UserProfile)
        cls.evaluation2 = mommy.make(Evaluation, participants=[cls.participant2])
        cls.contributor2 = mommy.make(UserProfile)
        cls.contribution2 = mommy.make(Contribution, contributor=cls.contributor2, evaluation=cls.evaluation2)

    def test_import_existing_contributor(self):
        self.assertEqual(self.evaluation1.contributions.count(), 2)

        success_messages, warnings, __ = PersonImporter.process_source_evaluation('contributor', self.evaluation1, test_run=True, source_evaluation=self.evaluation1)
        self.assertIn("0 contributors would be added to the evaluation", "".join(success_messages))
        self.assertIn("The following 1 users are already contributing to evaluation", warnings[ExcelImporter.W_GENERAL][0])

        success_messages, warnings, __ = PersonImporter.process_source_evaluation('contributor', self.evaluation1, test_run=False, source_evaluation=self.evaluation1)
        self.assertIn("0 contributors added to the evaluation", "".join(success_messages))
        self.assertIn("The following 1 users are already contributing to evaluation", warnings[ExcelImporter.W_GENERAL][0])

        self.assertEqual(self.evaluation1.contributions.count(), 2)
        self.assertEqual(set(UserProfile.objects.filter(contributions__evaluation=self.evaluation1)), set([self.contributor1]))

    def test_import_new_contributor(self):
        self.assertEqual(self.evaluation1.contributions.count(), 2)

        success_messages, __, __ = PersonImporter.process_source_evaluation('contributor', self.evaluation1, test_run=True, source_evaluation=self.evaluation2)
        self.assertIn("1 contributors would be added to the evaluation", "".join(success_messages))
        self.assertIn("{}".format(self.contributor2.full_name), "".join(success_messages))

        self.assertEqual(self.evaluation1.contributions.count(), 2)

        success_messages, __, __ = PersonImporter.process_source_evaluation('contributor', self.evaluation1, test_run=False, source_evaluation=self.evaluation2)
        self.assertIn("1 contributors added to the evaluation", "".join(success_messages))
        self.assertIn("{}".format(self.contributor2.full_name), "".join(success_messages))

        self.assertEqual(self.evaluation1.contributions.count(), 3)
        self.assertEqual(set(UserProfile.objects.filter(contributions__evaluation=self.evaluation1)), set([self.contributor1, self.contributor2]))

    def test_import_existing_participant(self):
        success_messages, warnings, __ = PersonImporter.process_source_evaluation('participant', self.evaluation1, test_run=True, source_evaluation=self.evaluation1)
        self.assertIn("0 participants would be added to the evaluation", "".join(success_messages))
        self.assertIn("The following 1 users are already participants in evaluation", warnings[ExcelImporter.W_GENERAL][0])

        success_messages, warnings, __ = PersonImporter.process_source_evaluation('participant', self.evaluation1, test_run=False, source_evaluation=self.evaluation1)
        self.assertIn("0 participants added to the evaluation", "".join(success_messages))
        self.assertIn("The following 1 users are already participants in evaluation", warnings[ExcelImporter.W_GENERAL][0])

        self.assertEqual(self.evaluation1.participants.count(), 1)
        self.assertEqual(self.evaluation1.participants.get(), self.participant1)

    def test_import_new_participant(self):
        success_messages, __, __ = PersonImporter.process_source_evaluation('participant', self.evaluation1, test_run=True, source_evaluation=self.evaluation2)
        self.assertIn("1 participants would be added to the evaluation", "".join(success_messages))
        self.assertIn("{}".format(self.participant2.full_name), "".join(success_messages))

        success_messages, __, __ = PersonImporter.process_source_evaluation('participant', self.evaluation1, test_run=False, source_evaluation=self.evaluation2)
        self.assertIn("1 participants added to the evaluation", "".join(success_messages))
        self.assertIn("{}".format(self.participant2.full_name), "".join(success_messages))

        self.assertEqual(self.evaluation1.participants.count(), 2)
        self.assertEqual(set(self.evaluation1.participants.all()), set([self.participant1, self.participant2]))
