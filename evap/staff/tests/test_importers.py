import os
from datetime import date, datetime
import io
import xlwt
from django.test import TestCase, override_settings
from django.conf import settings
from model_bakery import baker

from evap.evaluation.models import Course, Degree, UserProfile, Semester, Evaluation, Contribution, CourseType
from evap.staff.importers import UserImporter, EnrollmentImporter, PersonImporter, ImporterError, ImporterWarning
from evap.staff.tools import ImportType
import evap.staff.fixtures.excel_files_test_data as excel_data


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
        cls.duplicate_excel_content = excel_data.create_memory_excel_file(excel_data.duplicate_user_import_filedata)

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
        self.assertIn('Successfully created 2 users:<br />Lucilia Manilium (lucilia.manilium@institution.example.com)<br />Bastius Quid (bastius.quid@external.example.com)', success_messages)
        self.assertIn('Successfully read Excel file.', success_messages)
        self.assertEqual(warnings, {})
        self.assertEqual(errors, {})

        self.assertEqual(len(user_list), 2)
        self.assertEqual(UserProfile.objects.count(), 2 + original_user_count)
        self.assertTrue(isinstance(user_list[0], UserProfile))
        self.assertTrue(UserProfile.objects.filter(email="lucilia.manilium@institution.example.com").exists())
        self.assertTrue(UserProfile.objects.filter(email="bastius.quid@external.example.com").exists())

    def test_duplicate_warning(self):
        baker.make(UserProfile, first_name='Lucilia', last_name="Manilium", email="luma@institution.example.com")

        __, __, warnings_test, __ = UserImporter.process(self.valid_excel_content, test_run=True)
        __, __, warnings_no_test, __ = UserImporter.process(self.valid_excel_content, test_run=False)

        self.assertEqual(warnings_test, warnings_no_test)
        self.assertEqual(warnings_test[ImporterWarning.DUPL], [
            "An existing user has the same first and last name as a new user:<br />"
            " -  Lucilia Manilium, luma@institution.example.com (existing)<br />"
            " -  Lucilia Manilium, lucilia.manilium@institution.example.com (new)"])

    def test_ignored_duplicate_warning(self):
        __, __, warnings_test, __ = UserImporter.process(self.duplicate_excel_content, test_run=True)
        __, __, warnings_no_test, __ = UserImporter.process(self.duplicate_excel_content, test_run=False)

        self.assertEqual(warnings_test, warnings_no_test)
        self.assertEqual(warnings_test[ImporterWarning.IGNORED], [
            "The duplicated row 4 in sheet 'Users' was ignored. It was first found in sheet 'Users' on row 3."])

    def test_random_file_error(self):
        original_user_count = UserProfile.objects.count()

        __, __, __, errors_test = UserImporter.process(self.random_excel_content, test_run=True)
        __, __, __, errors_no_test = UserImporter.process(self.random_excel_content, test_run=False)

        self.assertEqual(errors_test, errors_no_test)
        self.assertEqual(errors_test[ImporterError.SCHEMA], [
            "Couldn't read the file. Error: Unsupported format, or corrupt file: Expected BOF record; found b'42\\n'"])
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_invalid_file_error(self):
        original_user_count = UserProfile.objects.count()

        __, __, __, errors_test = UserImporter.process(self.invalid_excel_content, test_run=True)
        __, __, __, errors_no_test = UserImporter.process(self.invalid_excel_content, test_run=False)

        self.assertEqual(errors_test, errors_no_test)
        self.assertEqual(errors_test[ImporterError.USER], ['Sheet "Sheet1", row 2: Email address is missing.'])
        self.assertEqual(errors_test[ImporterError.GENERAL], [
            'Errors occurred while parsing the input data. No data was imported.'])
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_import_makes_inactive_user_active(self):
        baker.make(UserProfile, email="lucilia.manilium@institution.example.com", is_active=False)

        __, __, warnings_test, __ = UserImporter.process(self.valid_excel_content, test_run=True)
        self.assertEqual(warnings_test[ImporterWarning.INACTIVE], [
            "The following user is currently marked inactive and will be marked active upon importing: "
            " None None, lucilia.manilium@institution.example.com"])

        __, __, warnings_no_test, __ = UserImporter.process(self.valid_excel_content, test_run=False)
        self.assertEqual(warnings_no_test[ImporterWarning.INACTIVE], [
            "The following user was previously marked inactive and is now marked active upon importing: "
            " None None, lucilia.manilium@institution.example.com"])

        self.assertEqual(UserProfile.objects.count(), 2)


class TestEnrollmentImporter(TestCase):
    filename_random = os.path.join(settings.BASE_DIR, "staff/fixtures/random.random")

    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester)
        cls.vote_start_datetime = datetime(2017, 1, 10)
        cls.vote_end_date = date(2017, 3, 10)
        baker.make(CourseType, name_de="Seminar", import_names=["Seminar", "S"])
        baker.make(CourseType, name_de="Vorlesung", import_names=["Vorlesung", "V"])
        degree_bachelor = Degree.objects.get(name_de="Bachelor")
        degree_bachelor.import_names = ["Bachelor", "B. Sc."]
        degree_bachelor.save()
        degree_master = Degree.objects.get(name_de="Master")
        degree_master.import_names = ["Master", "M. Sc."]
        degree_master.save()

    def test_valid_file_import(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata)

        success_messages, warnings, errors = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        self.assertIn("The import run will create 23 courses/evaluations and 23 users:", "".join(success_messages))
        # check for one random user instead of for all 23
        self.assertIn("Ferdi Itaque (789@institution.example.com)", "".join(success_messages))
        self.assertEqual(errors, {})
        self.assertEqual(warnings, {})

        old_user_count = UserProfile.objects.all().count()

        success_messages, warnings, errors = EnrollmentImporter.process(excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False)
        self.assertIn("Successfully created 23 courses/evaluations, 6 students and 17 contributors:", "".join(success_messages))
        self.assertIn("Ferdi Itaque (789@institution.example.com)", "".join(success_messages))
        self.assertEqual(errors, {})
        self.assertEqual(warnings, {})

        self.assertEqual(Evaluation.objects.all().count(), 23)
        expected_user_count = old_user_count + 23
        self.assertEqual(UserProfile.objects.all().count(), expected_user_count)

    def test_degrees_are_merged(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_degree_merge_filedata)

        success_messages, warnings_test, errors = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        self.assertIn("The import run will create 1 courses/evaluations and 3 users", "".join(success_messages))
        self.assertEqual(errors, {})
        self.assertEqual(warnings_test[ImporterWarning.DEGREE], [
            'Sheet "MA Belegungen", row 3: The course\'s "Build" degree differs from it\'s degree in a previous row. '
            'Both degrees have been set for the course.'])
        self.assertEqual(len(warnings_test), 1)

        success_messages, warnings_no_test, errors = EnrollmentImporter.process(excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False)
        self.assertIn("Successfully created 1 courses/evaluations, 2 students and 1 contributors", "".join(success_messages))
        self.assertEqual(errors, {})
        self.assertEqual(warnings_no_test, warnings_test)

        self.assertEqual(Course.objects.all().count(), 1)
        self.assertEqual(Evaluation.objects.all().count(), 1)

        course = Course.objects.get(name_de="Bauen")
        self.assertSetEqual(set(course.degrees.all()), set(Degree.objects.filter(name_de__in=["Master", "Bachelor"])))

    def test_course_type_and_degrees_are_retrieved_with_import_names(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_import_names_filedata)

        success_messages, warnings, errors = EnrollmentImporter.process(excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False)
        self.assertIn("Successfully created 2 courses/evaluations, 4 students and 2 contributors:", "".join(success_messages))
        self.assertEqual(errors, {})
        self.assertEqual(warnings, {})

        self.assertEqual(Course.objects.all().count(), 2)
        course_spelling = Course.objects.get(name_en="Spelling")
        self.assertEqual(course_spelling.type.name_de, "Vorlesung")
        self.assertEqual(list(course_spelling.degrees.values_list("name_en", flat=True)), ["Bachelor"])
        course_build = Course.objects.get(name_en="Build")
        self.assertEqual(course_build.type.name_de, "Seminar")
        self.assertEqual(list(course_build.degrees.values_list("name_en", flat=True)), ["Master"])

    @override_settings(IMPORTER_MAX_ENROLLMENTS=1)
    def test_enrollment_importer_high_enrollment_warning(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata)

        __, warnings_test, __ = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        __, warnings_no_test, __ = EnrollmentImporter.process(excel_content, self.semester, self.vote_start_datetime, self.vote_end_date, test_run=False)

        self.assertEqual(warnings_test, warnings_no_test)
        self.assertCountEqual(warnings_test[ImporterWarning.MANY], {
            "Warning: User ipsum.lorem@institution.example.com has 6 enrollments, which is a lot.",
            "Warning: User lucilia.manilium@institution.example.com has 6 enrollments, which is a lot.",
            "Warning: User diam.synephebos@institution.example.com has 6 enrollments, which is a lot.",
            "Warning: User torquate.metrodorus@institution.example.com has 6 enrollments, which is a lot.",
            "Warning: User latinas.menandri@institution.example.com has 5 enrollments, which is a lot.",
            "Warning: User bastius.quid@external.example.com has 4 enrollments, which is a lot."})

    def test_random_file_error(self):
        with open(self.filename_random, "rb") as excel_file:
            excel_content = excel_file.read()

        original_user_count = UserProfile.objects.count()

        __, __, errors_test = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        __, __, errors_no_test = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=False)

        self.assertEqual(errors_test, errors_no_test)
        self.assertEqual(errors_test[ImporterError.SCHEMA], [
            "Couldn't read the file. Error: Unsupported format, or corrupt file: Expected BOF record; found b'42\\n'"])
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_invalid_file_error(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.invalid_enrollment_data_filedata)

        original_user_count = UserProfile.objects.count()

        __, __, errors_test = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        __, __, errors_no_test = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=False)

        self.assertEqual(errors_test, errors_no_test)
        self.assertCountEqual(errors_test[ImporterError.USER], {
            'Sheet "MA Belegungen", row 3: The users\'s data (email: bastius.quid@external.example.com) differs from it\'s data in a previous row.',
            'Sheet "MA Belegungen", row 7: Email address is missing.',
            'Sheet "MA Belegungen", row 10: Email address is missing.'})
        self.assertCountEqual(errors_test[ImporterError.COURSE], {
            'Sheet "MA Belegungen", row 18: The German name for course "Bought" already exists for another course.',
            'Sheet "MA Belegungen", row 20: The course\'s "Cost" data differs from it\'s data in a previous row.'})
        self.assertEqual(errors_test[ImporterError.DEGREE_MISSING], [
            'Error: No degree is associated with the import name "Diploma". Please manually create it first.'])
        self.assertEqual(errors_test[ImporterError.COURSE_TYPE_MISSING], [
            'Error: No course type is associated with the import name "Praktikum". Please manually create it first.'])
        self.assertEqual(errors_test[ImporterError.IS_GRADED], [
            '"is_graded" of course Deal is maybe, but must be yes or no'])
        self.assertEqual(errors_test[ImporterError.GENERAL], [
            'Errors occurred while parsing the input data. No data was imported.'])
        self.assertEqual(len(errors_test), 6)
        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_duplicate_course_error(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata)

        semester = baker.make(Semester)
        baker.make(Course, name_de="Stehlen", name_en="Stehlen", semester=semester)
        baker.make(Course, name_de="Shine", name_en="Shine", semester=semester)

        __, __, errors = EnrollmentImporter.process(excel_content, semester, None, None, test_run=False)

        self.assertCountEqual(errors[ImporterError.COURSE], {
            "Course Stehlen does already exist in this semester.",
            "Course Shine does already exist in this semester."})

    def test_replace_consecutive_and_trailing_spaces(self):
        excel_content = excel_data.create_memory_excel_file(excel_data.test_enrollment_data_consecutive_and_trailing_spaces_filedata)

        success_messages, __, __ = EnrollmentImporter.process(excel_content, self.semester, None, None, test_run=True)
        self.assertIn("The import run will create 1 courses/evaluations and 3 users", "".join(success_messages))


class TestPersonImporter(TestCase):
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

        success_messages, warnings, __ = PersonImporter.process_source_evaluation(ImportType.Contributor, self.evaluation1,
                                                                                  test_run=True, source_evaluation=self.evaluation1)
        self.assertIn("0 contributors would be added to the evaluation", "".join(success_messages))
        self.assertIn("The following 1 users are already contributing to evaluation", warnings[ImporterWarning.GENERAL][0])

        success_messages, warnings, __ = PersonImporter.process_source_evaluation(ImportType.Contributor, self.evaluation1,
                                                                                  test_run=False, source_evaluation=self.evaluation1)
        self.assertIn("0 contributors added to the evaluation", "".join(success_messages))
        self.assertIn("The following 1 users are already contributing to evaluation", warnings[ImporterWarning.GENERAL][0])

        self.assertEqual(self.evaluation1.contributions.count(), 2)
        self.assertEqual(set(UserProfile.objects.filter(contributions__evaluation=self.evaluation1)), set([self.contributor1]))

    def test_import_new_contributor(self):
        self.assertEqual(self.evaluation1.contributions.count(), 2)

        success_messages, __, __ = PersonImporter.process_source_evaluation(ImportType.Contributor, self.evaluation1,
                                                                            test_run=True, source_evaluation=self.evaluation2)
        self.assertIn("1 contributors would be added to the evaluation", "".join(success_messages))
        self.assertIn("{}".format(self.contributor2.email), "".join(success_messages))

        self.assertEqual(self.evaluation1.contributions.count(), 2)

        success_messages, __, __ = PersonImporter.process_source_evaluation(ImportType.Contributor, self.evaluation1,
                                                                            test_run=False, source_evaluation=self.evaluation2)
        self.assertIn("1 contributors added to the evaluation", "".join(success_messages))
        self.assertIn("{}".format(self.contributor2.email), "".join(success_messages))

        self.assertEqual(self.evaluation1.contributions.count(), 3)
        self.assertEqual(set(UserProfile.objects.filter(contributions__evaluation=self.evaluation1)), set([self.contributor1, self.contributor2]))

    def test_import_existing_participant(self):
        success_messages, warnings, __ = PersonImporter.process_source_evaluation(ImportType.Participant, self.evaluation1,
                                                                                  test_run=True, source_evaluation=self.evaluation1)
        self.assertIn("0 participants would be added to the evaluation", "".join(success_messages))
        self.assertIn("The following 1 users are already participants in evaluation", warnings[ImporterWarning.GENERAL][0])

        success_messages, warnings, __ = PersonImporter.process_source_evaluation(ImportType.Participant, self.evaluation1,
                                                                                  test_run=False, source_evaluation=self.evaluation1)
        self.assertIn("0 participants added to the evaluation", "".join(success_messages))
        self.assertIn("The following 1 users are already participants in evaluation", warnings[ImporterWarning.GENERAL][0])

        self.assertEqual(self.evaluation1.participants.count(), 1)
        self.assertEqual(self.evaluation1.participants.get(), self.participant1)

    def test_import_new_participant(self):
        success_messages, __, __ = PersonImporter.process_source_evaluation(ImportType.Participant, self.evaluation1,
                                                                            test_run=True, source_evaluation=self.evaluation2)
        self.assertIn("1 participants would be added to the evaluation", "".join(success_messages))
        self.assertIn("{}".format(self.participant2.email), "".join(success_messages))

        success_messages, __, __ = PersonImporter.process_source_evaluation(ImportType.Participant, self.evaluation1, test_run=False, source_evaluation=self.evaluation2)
        self.assertIn("1 participants added to the evaluation", "".join(success_messages))
        self.assertIn("{}".format(self.participant2.email), "".join(success_messages))

        self.assertEqual(self.evaluation1.participants.count(), 2)
        self.assertEqual(set(self.evaluation1.participants.all()), set([self.participant1, self.participant2]))
