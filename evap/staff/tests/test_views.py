import os

from django.conf import settings
from django.contrib.auth.models import Group
from django.test.utils import override_settings
from django_webtest import WebTest
from model_mommy import mommy

from evap.evaluation.models import Semester, UserProfile, Course
from evap.evaluation.tests.test_utils import lastform


@override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com", "student.institution.com"])
class TestSemesterCourseImportParticipantsView(WebTest):
    @classmethod
    def setUpTestData(cls):
        mommy.make(Semester, pk=1)
        mommy.make(UserProfile, username="user", groups=[Group.objects.get(name="Staff")])
        cls.course = mommy.make(Course, pk=1)

    def test_import_valid_file(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='user')

        original_participant_count = self.course.participants.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)
        form.submit(name="operation", value="import")

        self.assertEqual(self.course.participants.count(), original_participant_count + 2)

    def test_import_invalid_file(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='user')

        original_user_count = UserProfile.objects.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls"),)

        reply = form.submit(name="operation", value="import")

        self.assertContains(reply, 'Sheet &quot;Sheet1&quot;, row 2: Email address is missing.')
        self.assertContains(reply, 'Errors occurred while parsing the input data. No data was imported.')

        self.assertEquals(UserProfile.objects.count(), original_user_count)

    def test_test_run(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='user')

        original_participant_count = self.course.participants.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)
        form.submit(name="operation", value="test")

        self.assertEqual(self.course.participants.count(), original_participant_count)

    def test_suspicious_operation(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='user')

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)
