import os

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.urlresolvers import reverse
from django.test.utils import override_settings
from django_webtest import WebTest
from model_mommy import mommy
import xlrd

from evap.evaluation.models import Semester, UserProfile, Course, CourseType, \
                                   TextAnswer, Contribution
from evap.evaluation.tests.test_utils import FuzzyInt, lastform, WebTest, ViewTest


class PerformanceTests(WebTest):

    def test_num_queries_user_list(self):
        """
            ensures that the number of queries in the user list is constant
            and not linear to the number of users
        """
        num_users = 50
        mommy.make(UserProfile, username="staff.user", groups=[Group.objects.get(name="Staff")])
        mommy.make(UserProfile, _quantity=num_users)

        with self.assertNumQueries(FuzzyInt(0, num_users-1)):
            self.app.get("/staff/user/", user="staff.user")


class TestUserBulkDeleteView(ViewTest):
    url = '/staff/user/bulk_delete'
    users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])

    def test_testrun_deletes_no_users(self):
        page = self.app.get(self.url, user='staff')
        form = lastform(page)

        form["username_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/test_user_bulk_delete_file.txt"),)

        users_before = UserProfile.objects.count()

        reply = form.submit(name="operation", value="test")

        # Not getting redirected after.
        self.assertEqual(reply.status_code, 200)
        # No user got deleted.
        self.assertEqual(users_before, UserProfile.objects.count())

    def test_deletes_users(self):
        mommy.make(UserProfile, username='testuser1')
        mommy.make(UserProfile, username='testuser2')
        contribution = mommy.make(Contribution)
        mommy.make(UserProfile, username='contributor', contributions=[contribution])
        page = self.app.get(self.url, user='staff')
        form = lastform(page)

        form["username_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/test_user_bulk_delete_file.txt"),)

        self.assertEqual(UserProfile.objects.filter(username__in=['testuser1', 'testuser2', 'contributor']).count(), 3)
        user_count_before = UserProfile.objects.count()

        reply = form.submit(name="operation", value="bulk_delete")

        # Getting redirected after.
        self.assertEqual(reply.status_code, 302)

        # Assert only these two users got deleted.
        self.assertEqual(UserProfile.objects.filter(username__in=['testuser1', 'testuser2']).count(), 0)
        self.assertTrue(UserProfile.objects.filter(username='contributor').exists())
        self.assertEqual(UserProfile.objects.count(), user_count_before - 2)


class TestSemesterExportView(ViewTest):
    url = '/staff/semester/1/export'
    users = ['staff']

    def setUp(self):
        self.semester = mommy.make(Semester)
        self.course_type = mommy.make(CourseType)
        self.course = mommy.make(Course, type=self.course_type, semester=self.semester)
        mommy.make(UserProfile, username="staff", groups=[Group.objects.get(name="Staff")])

    def test_view_downloads_excel_file(self):
        page = self.app.get('/staff/semester/1/export', user='staff')
        form = lastform(page)

        # Check one course type.
        form.set('form-0-selected_course_types', 'id_form-0-selected_course_types_0')

        response = form.submit()

        # Load response as Excel file and check its heading for correctness.
        workbook = xlrd.open_workbook(file_contents=response.content)
        self.assertEquals(workbook.sheets()[0].row_values(0)[0],
                          'Evaluation {0}\n\n{1}'.format(self.semester.name, ", ".join([self.course_type.name])))


@override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com", "student.institution.com"])
class TestSemesterCourseImportParticipantsView(WebTest):
    @classmethod
    def setUpTestData(cls):
        mommy.make(Semester, pk=1)
        mommy.make(UserProfile, username="staff", groups=[Group.objects.get(name="Staff")])
        cls.course = mommy.make(Course, pk=1)

    def test_import_valid_file(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='staff')

        original_participant_count = self.course.participants.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)
        form.submit(name="operation", value="import")

        self.assertEqual(self.course.participants.count(), original_participant_count + 2)

    def test_import_invalid_file(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='staff')

        original_user_count = UserProfile.objects.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls"),)

        reply = form.submit(name="operation", value="import")

        self.assertContains(reply, 'Sheet &quot;Sheet1&quot;, row 2: Email address is missing.')
        self.assertContains(reply, 'Errors occurred while parsing the input data. No data was imported.')

        self.assertEquals(UserProfile.objects.count(), original_user_count)

    def test_test_run(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='staff')

        original_participant_count = self.course.participants.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)
        form.submit(name="operation", value="test")

        self.assertEqual(self.course.participants.count(), original_participant_count)

    def test_suspicious_operation(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='staff')

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)


class TestCourseCommentsUpdatePublishView(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="staff.user", groups=[Group.objects.get(name="Staff")])
        mommy.make(Course, pk=1)

    def helper(self, old_state, expected_new_state, action):
        textanswer = mommy.make(TextAnswer, state=old_state)
        response = self.app.post(reverse("staff:course_comments_update_publish"), {"id": textanswer.id, "action": action, "course_id": 1}, user="staff.user")
        self.assertEqual(response.status_code, 200)
        textanswer.refresh_from_db()
        self.assertEqual(textanswer.state, expected_new_state)

    def test_review_actions(self):
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PUBLISHED, "publish")
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.HIDDEN, "hide")
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PRIVATE, "make_private")
        self.helper(TextAnswer.PUBLISHED, TextAnswer.NOT_REVIEWED, "unreview")


class ArchivingTests(WebTest):

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester)
        cls.course = mommy.make(Course, pk=7, state="published", semester=cls.semester)

        users = mommy.make(UserProfile, _quantity=3)
        cls.course.participants = users
        cls.course.voters = users[:2]

    def get_assert_403(self, url, user):
        try:
            self.app.get(url, user=user, status=403)
        except AppError as e:
            self.fail('url "{}" failed with user "{}"'.format(url, user))

    def test_raise_403(self):
        """
            Tests whether inaccessible views on archived semesters/courses correctly raise a 403.
        """
        self.semester.archive()

        semester_url = "/staff/semester/{}/".format(self.semester.pk)

        self.get_assert_403(semester_url + "import", "evap")
        self.get_assert_403(semester_url + "assign", "evap")
        self.get_assert_403(semester_url + "course/create", "evap")
        self.get_assert_403(semester_url + "courseoperation", "evap")
