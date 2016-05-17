import datetime
import os

from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.core.urlresolvers import reverse
from django.test.utils import override_settings
from model_mommy import mommy
import xlrd

from evap.evaluation.models import Semester, UserProfile, Course, CourseType, TextAnswer, Contribution, Questionnaire, \
                                   Question
from evap.evaluation.tests.tools import FuzzyInt, WebTest, ViewTest


class TestUserIndexView(ViewTest):
    url = '/staff/user/'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])

    def test_num_queries_is_constant(self):
        """
            ensures that the number of queries in the user list is constant
            and not linear to the number of users
        """
        num_users = 50
        semester = mommy.make(Semester, is_archived=True)
        course = mommy.make(Course, state="published", semester=semester, _participant_count=1, _voter_count=1)  # this triggers more checks in UserProfile.can_staff_delete
        mommy.make(UserProfile, _quantity=num_users, courses_participating_in=[course])

        with self.assertNumQueries(FuzzyInt(0, num_users - 1)):
            self.app.get(self.url, user="staff")


class TestUserBulkDeleteView(ViewTest):
    url = '/staff/user/bulk_delete'
    test_users = ['staff']
    filename = os.path.join(settings.BASE_DIR, "staff/fixtures/test_user_bulk_delete_file.txt")

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])

    def test_testrun_deletes_no_users(self):
        page = self.app.get(self.url, user='staff')
        form = page.forms["user-bulk-delete-form"]

        form["username_file"] = (self.filename,)

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
        form = page.forms["user-bulk-delete-form"]

        form["username_file"] = (self.filename,)

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
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        cls.semester = mommy.make(Semester)
        cls.course_type = mommy.make(CourseType)
        cls.course = mommy.make(Course, pk=1, type=cls.course_type, semester=cls.semester)

    def test_view_downloads_excel_file(self):
        page = self.app.get(self.url, user='staff')
        form = page.forms["semester-export-form"]

        # Check one course type.
        form.set('form-0-selected_course_types', 'id_form-0-selected_course_types_0')

        response = form.submit()

        # Load response as Excel file and check its heading for correctness.
        workbook = xlrd.open_workbook(file_contents=response.content)
        self.assertEqual(workbook.sheets()[0].row_values(0)[0],
                         'Evaluation {0}\n\n{1}'.format(self.semester.name, ", ".join([self.course_type.name])))


@override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com", "student.institution.com"])
class TestSemesterCourseImportParticipantsView(ViewTest):
    url = "/staff/semester/1/course/1/participant_import"
    test_users = ["staff"]
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls")
    filename_invalid = os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls")

    @classmethod
    def setUpTestData(cls):
        semester = mommy.make(Semester, pk=1)
        mommy.make(UserProfile, username="staff", groups=[Group.objects.get(name="Staff")])
        cls.course = mommy.make(Course, pk=1, semester=semester)

    def test_import_valid_file(self):
        page = self.app.get(self.url, user='staff')

        original_participant_count = self.course.participants.count()

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)
        form.submit(name="operation", value="import")

        self.assertEqual(self.course.participants.count(), original_participant_count + 2)

    def test_import_invalid_file(self):
        page = self.app.get(self.url, user='staff')

        original_user_count = UserProfile.objects.count()

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_invalid,)

        reply = form.submit(name="operation", value="import")

        self.assertContains(reply, 'Sheet &quot;Sheet1&quot;, row 2: Email address is missing.')
        self.assertContains(reply, 'Errors occurred while parsing the input data. No data was imported.')

        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_test_run(self):
        page = self.app.get(self.url, user='staff')

        original_participant_count = self.course.participants.count()

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)
        form.submit(name="operation", value="test")

        self.assertEqual(self.course.participants.count(), original_participant_count)

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user='staff')

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)


class TestCourseCommentsUpdatePublishView(WebTest):
    url = reverse("staff:course_comments_update_publish")
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="staff.user", groups=[Group.objects.get(name="Staff")])
        mommy.make(Course, pk=1)

    def helper(self, old_state, expected_new_state, action):
        textanswer = mommy.make(TextAnswer, state=old_state)
        response = self.app.post(self.url, {"id": textanswer.id, "action": action, "course_id": 1}, user="staff.user")
        self.assertEqual(response.status_code, 200)
        textanswer.refresh_from_db()
        self.assertEqual(textanswer.state, expected_new_state)

    def test_review_actions(self):
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PUBLISHED, "publish")
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.HIDDEN, "hide")
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PRIVATE, "make_private")
        self.helper(TextAnswer.PUBLISHED, TextAnswer.NOT_REVIEWED, "unreview")


class ArchivingTests(WebTest):

    def test_raise_403(self):
        """
            Tests whether inaccessible views on archived semesters/courses correctly raise a 403.
        """
        semester = mommy.make(Semester, is_archived=True)

        semester_url = "/staff/semester/{}/".format(semester.pk)

        self.get_assert_403(semester_url + "import", "evap")
        self.get_assert_403(semester_url + "assign", "evap")
        self.get_assert_403(semester_url + "course/create", "evap")
        self.get_assert_403(semester_url + "courseoperation", "evap")


class TestQuestionnaireNewVersionView(ViewTest):
    url = '/staff/questionnaire/2/new_version'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        cls.name_de_orig = 'kurzer name'
        cls.name_en_orig = 'short name'
        questionnaire = mommy.make(Questionnaire, id=2, name_de=cls.name_de_orig, name_en=cls.name_en_orig)
        mommy.make(Question, questionnaire=questionnaire)
        mommy.make(UserProfile, username="staff", groups=[Group.objects.get(name="Staff")])

    def test_changes_old_title(self):
        page = self.app.get(url=self.url, user='staff')
        form = page.forms['questionnaire-form']

        form.submit()

        timestamp = datetime.date.today()
        new_name_de = '{} (until {})'.format(self.name_de_orig, str(timestamp))
        new_name_en = '{} (until {})'.format(self.name_en_orig, str(timestamp))

        self.assertTrue(Questionnaire.objects.filter(name_de=self.name_de_orig, name_en=self.name_en_orig).exists())
        self.assertTrue(Questionnaire.objects.filter(name_de=new_name_de, name_en=new_name_en).exists())

    def test_no_second_update(self):

        # First save.
        page = self.app.get(url=self.url, user='staff')
        form = page.forms['questionnaire-form']
        form.submit()

        # Second try.
        new_questionnaire = Questionnaire.objects.get(name_de=self.name_de_orig)
        page = self.app.get(url='/staff/questionnaire/{}/new_version'.format(new_questionnaire.id), user='staff')

        # We should get redirected back to the questionnaire index.
        self.assertEqual(page.status_code, 302)  # REDIRECT
        self.assertEqual(page.location, '/staff/questionnaire/')


class TestSemesterRawDataExportView(ViewTest):
    url = '/staff/semester/1/raw_export'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        cls.student_user = mommy.make(UserProfile, username='student')
        cls.semester = mommy.make(Semester)
        cls.course_type = mommy.make(CourseType, name_en="Type")
        cls.course1 = mommy.make(Course, type=cls.course_type, semester=cls.semester, participants=[cls.student_user],
            voters=[cls.student_user], name_de="Veranstaltung 1", name_en="Course 1")
        cls.course2 = mommy.make(Course, type=cls.course_type, semester=cls.semester, participants=[cls.student_user],
            name_de="Veranstaltung 2", name_en="Course 2")
        mommy.make(Contribution, course=cls.course1, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=cls.course2, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

    def test_view_downloads_csv_file(self):
        response = self.app.get(self.url, user='staff')
        expected_content = (
            "Name;Degrees;Type;Single result;State;#Voters;#Participants;#Comments;Average grade\r\n"
            "Course 1;;Type;False;new;1;1;0;\r\n"
            "Course 2;;Type;False;new;0;1;0;\r\n"
        )
        self.assertEqual(response.content, expected_content.encode("utf-8"))


class TestSemesterParticipationDataExportView(ViewTest):
    url = '/staff/semester/1/participation_export'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        cls.student_user = mommy.make(UserProfile, username='student')
        cls.semester = mommy.make(Semester)
        cls.course_type = mommy.make(CourseType, name_en="Type")
        cls.course1 = mommy.make(Course, type=cls.course_type, semester=cls.semester, participants=[cls.student_user],
            voters=[cls.student_user], name_de="Veranstaltung 1", name_en="Course 1", is_required_for_reward=True)
        cls.course2 = mommy.make(Course, type=cls.course_type, semester=cls.semester, participants=[cls.student_user],
            name_de="Veranstaltung 2", name_en="Course 2", is_required_for_reward=False)
        mommy.make(Contribution, course=cls.course1, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=cls.course2, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

    def test_view_downloads_csv_file(self):
        response = self.app.get(self.url, user='staff')
        expected_content = (
            "Username;Can use reward points;#Required courses voted for;#Required courses;#Optional courses voted for;"
            "#Optional courses;Earned reward points\r\n"
            "student;False;1;1;0;1;False\r\n")
        self.assertEqual(response.content, expected_content.encode("utf-8"))


class TestSemesterDeleteView(ViewTest):
    url = '/staff/semester/delete'
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])

    def test_failure(self):
        semester = mommy.make(Semester, pk=1)
        mommy.make(Course, semester=semester, state='in_evaluation', voters=[mommy.make(UserProfile)])
        self.assertFalse(semester.can_staff_delete)
        response = self.app.post(self.url, {'semester_id': 1}, user='staff', expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Semester.objects.filter(pk=1).exists())

    def test_success(self):
        semester = mommy.make(Semester, pk=1)
        self.assertTrue(semester.can_staff_delete)
        response = self.app.post(self.url, {'semester_id': 1}, user='staff')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Semester.objects.filter(pk=1).exists())


class TestCourseCreateView(ViewTest):
    url = '/staff/semester/1/course/create'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        mommy.make(Semester, pk=1)
        mommy.make(CourseType)
        mommy.make(Questionnaire, pk=1, is_for_contributors=False)
        mommy.make(Questionnaire, pk=2, is_for_contributors=True)

    def test_course_create(self):
        """
            Tests the course creation view with one valid and one invalid input dataset.
        """
        response = self.get_assert_200("/staff/semester/1/course/create", "staff")
        form = response.forms["course-form"]
        form["name_de"] = "lfo9e7bmxp1xi"
        form["name_en"] = "asdf"
        form["type"] = 1
        form["degrees"] = ["1"]
        form["vote_start_date"] = "02/1/2099"
        form["vote_end_date"] = "02/1/2014"  # wrong order to get the validation error
        form["general_questions"] = ["1"]

        form['contributions-TOTAL_FORMS'] = 1
        form['contributions-INITIAL_FORMS'] = 0
        form['contributions-MAX_NUM_FORMS'] = 5
        form['contributions-0-course'] = ''
        form['contributions-0-contributor'] = 1
        form['contributions-0-questionnaires'] = [2]
        form['contributions-0-order'] = 0
        form['contributions-0-responsibility'] = "RESPONSIBLE"
        form['contributions-0-comment_visibility'] = "ALL"

        form.submit()
        self.assertFalse(Course.objects.exists())

        form["vote_start_date"] = "02/1/2014"
        form["vote_end_date"] = "02/1/2099"  # now do it right

        form.submit()
        self.assertEqual(Course.objects.get().name_de, "lfo9e7bmxp1xi")


class TestSingleResultCreateView(ViewTest):
    url = '/staff/semester/1/singleresult/create'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        mommy.make(Semester, pk=1)
        mommy.make(CourseType)

    def test_single_result_create(self):
        """
            Tests the single result creation view with one valid and one invalid input dataset.
        """
        response = self.get_assert_200(self.url, "staff")
        form = response.forms["single-result-form"]
        form["name_de"] = "qwertz"
        form["name_en"] = "qwertz"
        form["type"] = 1
        form["degrees"] = ["1"]
        form["event_date"] = "02/1/2014"
        form["answer_1"] = 6
        form["answer_3"] = 2
        # missing responsible to get a validation error

        form.submit()
        self.assertFalse(Course.objects.exists())

        form["responsible"] = 1  # now do it right

        form.submit()
        self.assertEqual(Course.objects.get().name_de, "qwertz")


class TestCourseEmailView(ViewTest):
    url = '/staff/semester/1/course/1/email'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        semester = mommy.make(Semester, pk=1)
        participant1 = mommy.make(UserProfile, email="foo@example.com")
        participant2 = mommy.make(UserProfile, email="bar@example.com")
        course = mommy.make(Course, pk=1, semester=semester, participants=[participant1, participant2])
        mommy.make(Contribution, course=course, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

    def test_course_email(self):
        """
            Tests whether the course email view actually sends emails.
        """
        page = self.get_assert_200(self.url, user="staff")
        form = page.forms["course-email-form"]
        form.get("recipients", index=0).checked = True  # send to all participants
        form["subject"] = "asdf"
        form["body"] = "asdf"
        form.submit()

        self.assertEqual(len(mail.outbox), 2)

class TestQuestionnaireDeletionView(WebTest):
    url = "/staff/questionnaire/delete"
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        questionnaire1 = mommy.make(Questionnaire, pk=1)
        questionnaire2 = mommy.make(Questionnaire, pk=2)
        mommy.make(Contribution, questionnaires=[questionnaire1])

    def test_questionnaire_deletion(self):
        """
            Tries to delete two questionnaires via the respective post request,
            only the second attempt should succeed.
        """
        self.assertFalse(Questionnaire.objects.get(pk=1).can_staff_delete)
        response = self.app.post("/staff/questionnaire/delete", {"questionnaire_id": 1}, user="staff", expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Questionnaire.objects.filter(pk=1).exists())

        self.assertTrue(Questionnaire.objects.get(pk=2).can_staff_delete)
        response = self.app.post("/staff/questionnaire/delete", {"questionnaire_id": 2}, user="staff")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Questionnaire.objects.filter(pk=2).exists())
