import os.path
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.test.utils import override_settings
from django.urls import reverse
from model_bakery import baker

from evap.evaluation.models import CourseType, Program, Semester, UserProfile
from evap.evaluation.tests.tools import TestCase, make_manager, submit_with_modal
from evap.staff.tests.utils import WebTestStaffMode


@override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com", "student.institution.com"])
class SampleTableImport(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        baker.make(CourseType, name_de="Vorlesung", name_en="Lecture", import_names=["Vorlesung"])
        baker.make(CourseType, name_de="Seminar", name_en="Seminar", import_names=["Seminar"])
        Program.objects.filter(name_de="Bachelor").update(import_names=["Bachelor", "B. Sc."])
        Program.objects.filter(name_de="Master").update(import_names=["Master", "M. Sc."])

    def test_sample_semester_file(self):
        page = self.app.get(reverse("staff:semester_import", args=[self.semester.pk]), user=self.manager)

        original_user_count = UserProfile.objects.count()

        form = page.forms["semester-import-form"]
        form["excel_file"] = (os.path.join(settings.MODULE, "static", "sample.xlsx"),)
        page = form.submit(name="operation", value="test")

        form = page.forms["semester-import-form"]
        form["vote_start_datetime"] = "2015-01-01 11:11:11"
        form["vote_end_date"] = "2099-01-01"
        submit_with_modal(page, form, name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 4)

    def test_sample_user_file(self):
        page = self.app.get("/staff/user/import", user=self.manager)

        original_user_count = UserProfile.objects.count()

        form = page.forms["user-import-form"]
        form["excel_file"] = (os.path.join(settings.MODULE, "static", "sample_user.xlsx"),)
        page = form.submit(name="operation", value="test")

        form = page.forms["user-import-form"]
        submit_with_modal(page, form, name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 2)


class TestMissingMigrations(TestCase):
    def test_for_missing_migrations(self):
        output = StringIO()
        try:
            call_command("makemigrations", dry_run=True, check=True, stdout=output)
        except SystemExit:
            self.fail("There are model changes not reflected in migrations, please run makemigrations.")
