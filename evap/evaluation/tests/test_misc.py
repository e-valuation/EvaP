import os.path
from io import StringIO

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings

from model_mommy import mommy

from evap.evaluation.models import Semester, UserProfile, CourseType
from evap.evaluation.tests.tools import WebTest

from django.urls import reverse

@override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com", "student.institution.com"])
class SampleXlsTests(WebTest):

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester)
        mommy.make(UserProfile, username="user", groups=[Group.objects.get(name="Staff")])
        mommy.make(CourseType, name_de="Vorlesung", name_en="Vorlesung")
        mommy.make(CourseType, name_de="Seminar", name_en="Seminar")

    def test_sample_xls(self):
        page = self.app.get(reverse("staff:semester_import", args=[self.semester.pk]), user='user')

        original_user_count = UserProfile.objects.count()

        form = page.forms["semester-import-form"]
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "static", "sample.xls"),)
        page = form.submit(name="operation", value="test")

        form = page.forms["semester-import-form"]
        form["vote_start_datetime"] = "2015-01-01 11:11:11"
        form["vote_end_date"] = "2099-01-01"
        form.submit(name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 4)

    def test_sample_user_xls(self):
        page = self.app.get("/staff/user/import", user='user')

        original_user_count = UserProfile.objects.count()

        form = page.forms["user-import-form"]
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "static", "sample_user.xls"),)
        page = form.submit(name="operation", value="test")

        form = page.forms["user-import-form"]
        form.submit(name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 2)


class TestDataTest(TestCase):

    def load_test_data(self):
        """
            Asserts that the test data still load cleanly.
            This test does not have the "test_" prefix, as it is meant
            to be started manually e.g. by Travis.
        """
        try:
            call_command("loaddata", "test_data", verbosity=0)
        except Exception:
            self.fail("Test data failed to load.")


class TestMissingMigrations(TestCase):
    def test_for_missing_migrations(self):
        output = StringIO()
        try:
            call_command('makemigrations', dry_run=True, check=True, stdout=output)
        except SystemExit:
            self.fail("There are model changes not reflected in migrations, please run makemigrations.")
