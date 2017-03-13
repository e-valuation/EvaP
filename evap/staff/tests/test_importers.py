import os
import datetime
from django.test import override_settings
from django.conf import settings
from evap.evaluation.tests.test_tools import WebTest
# from django.contrib.auth.models import Group
# from django.core import mail
# from django.urls import reverse
from model_mommy import mommy
# import xlrd

from evap.evaluation.models import UserProfile, Semester
# from evap.evaluation.models import Semester, UserProfile, Course, CourseType, TextAnswer, Contribution, \
#                                    Questionnaire, Question, EmailTemplate, Degree

from evap.staff.importers import UserImporter, EnrollmentImporter, ExcelImporter


class TestUserImporter(WebTest):
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls")

    def test_user_importer_duplicate_warning(self):
        mommy.make(UserProfile, first_name='Lucilia', last_name="Manilium", username="lucilia.manilium2")

        with open(self.filename_valid, "rb") as excel_file:
            excel_content = excel_file.read()

        __, __, warnings_test, __ = UserImporter.process(excel_content, test_run=True)
        __, __, warnings_no_test, __ = UserImporter.process(excel_content, test_run=False)

        self.assertEqual(warnings_test, warnings_no_test)
        self.assertIn("An existing user has the same first and last name as a new user:<br>"
                " - lucilia.manilium2 ( Lucilia Manilium, ) (existing)<br>"
                " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)",
                warnings_test[ExcelImporter.W_DUPL])

    def test_user_importer_email_mismatch_warning(self):
        mommy.make(UserProfile, email="42@42.de", username="lucilia.manilium")

        with open(self.filename_valid, "rb") as excel_file:
            excel_content = excel_file.read()

        __, __, warnings_test, __ = UserImporter.process(excel_content, test_run=True)
        __, __, warnings_no_test, __ = UserImporter.process(excel_content, test_run=False)
        self.assertEqual(warnings_test, warnings_no_test)
        self.assertIn("The existing user would be overwritten with the following data:<br>"
                " - lucilia.manilium ( None None, 42@42.de) (existing)<br>"
                " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)",
                warnings_test[ExcelImporter.W_EMAIL])


class TestEnrollmentImporter(WebTest):
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/test_enrollment_data.xls")

    @override_settings(IMPORTER_MAX_ENROLLMENTS=1)
    def test_enrollment_importer_high_enrollment_warning(self):
        semester = mommy.make(Semester)
        vote_start_date = datetime.datetime(2017, 1, 10)
        vote_end_date = datetime.datetime(2017, 3, 10)

        with open(self.filename_valid, "rb") as excel_file:
            excel_content = excel_file.read()

        __, warnings_test, __ = EnrollmentImporter.process(excel_content, semester, None, None, test_run=True)
        __, warnings_no_test, __ = EnrollmentImporter.process(excel_content, semester, vote_start_date, vote_end_date, test_run=False)

        self.assertEqual(warnings_test, warnings_no_test)
        warnings_many = warnings_test[EnrollmentImporter.W_MANY]
        self.assertIn("Warning: User ipsum.lorem has 6 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User lucilia.manilium has 6 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User diam.synephebos has 6 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User torquate.metrodorus has 6 enrollments, which is a lot.", warnings_many)
        self.assertIn("Warning: User latinas.menandri has 5 enrollments, which is a lot.", warnings_many)
