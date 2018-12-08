import datetime
import os
import glob

from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse
from django.test import override_settings
from django.test.testcases import TestCase

from django_webtest import WebTest
from model_mommy import mommy
import xlrd

from evap.evaluation.models import (Contribution, Course, CourseType, Degree, EmailTemplate, Evaluation, FaqSection,
                                    FaqQuestion, Question, Questionnaire, RatingAnswerCounter, Semester, TextAnswer,
                                    UserProfile)
from evap.evaluation.tests.tools import FuzzyInt, let_user_vote_for_evaluation, WebTestWith200Check
from evap.rewards.models import SemesterActivation, RewardPointGranting
from evap.staff.tools import generate_import_filename
from evap.staff.views import get_evaluations_with_prefetched_data


def helper_delete_all_import_files(user_id):
    file_filter = generate_import_filename(user_id, "*")
    for filename in glob.glob(file_filter):
        os.remove(filename)


# Staff - Sample Files View
class TestDownloadSampleXlsView(WebTest):
    url = '/staff/download_sample_xls/sample.xls'
    email_placeholder = "institution.com"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_sample_file_correctness(self):
        page = self.app.get(self.url, user='manager')

        found_institution_domains = 0
        book = xlrd.open_workbook(file_contents=page.body)
        for sheet in book.sheets():
            for row in sheet.get_rows():
                for cell in row:
                    value = cell.value
                    self.assertNotIn(self.email_placeholder, value)
                    if "@" + settings.INSTITUTION_EMAIL_DOMAINS[0] in value:
                        found_institution_domains += 1

        self.assertEqual(found_institution_domains, 2)


# Staff - Root View
class TestStaffIndexView(WebTestWith200Check):
    test_users = ['manager']
    url = '/staff/'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])


# Staff - FAQ View
class TestStaffFAQView(WebTestWith200Check):
    url = '/staff/faq/'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])


class TestStaffFAQEditView(WebTestWith200Check):
    url = '/staff/faq/1'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        section = mommy.make(FaqSection, pk=1)
        mommy.make(FaqQuestion, section=section)


# Staff - User Views
class TestUserIndexView(WebTest):
    url = '/staff/user/'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_num_queries_is_constant(self):
        """
            ensures that the number of queries in the user list is constant
            and not linear to the number of users
        """
        num_users = 50
        semester = mommy.make(Semester, participations_are_archived=True)
        evaluation = mommy.make(Evaluation, state="published", course=mommy.make(Course, semester=semester), _participant_count=1, _voter_count=1)  # this triggers more checks in UserProfile.can_manager_delete
        mommy.make(UserProfile, _quantity=num_users, evaluations_participating_in=[evaluation])

        with self.assertNumQueries(FuzzyInt(0, num_users - 1)):
            self.app.get(self.url, user="manager")


class TestUserCreateView(WebTest):
    url = "/staff/user/create"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_user_is_created(self):
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["user-form"]
        form["username"] = "mflkd862xmnbo5"
        form["first_name"] = "asd"
        form["last_name"] = "asd"
        form["email"] = "a@b.de"

        form.submit()

        self.assertEqual(UserProfile.objects.order_by("pk").last().username, "mflkd862xmnbo5")


@override_settings(REWARD_POINTS=[
    (1 / 3, 1),
    (2 / 3, 2),
    (3 / 3, 3),
])
class TestUserEditView(WebTest):
    url = "/staff/user/3/edit"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        mommy.make(UserProfile, pk=3)

    def test_questionnaire_edit(self):
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["user-form"]
        form["username"] = "lfo9e7bmxp1xi"
        form.submit()
        self.assertTrue(UserProfile.objects.filter(username='lfo9e7bmxp1xi').exists())

    def test_reward_points_granting_message(self):
        evaluation = mommy.make(Evaluation)
        already_evaluated = mommy.make(Evaluation, course=mommy.make(Course, semester=evaluation.course.semester))
        SemesterActivation.objects.create(semester=evaluation.course.semester, is_active=True)
        student = mommy.make(UserProfile, email="foo@institution.example.com",
            evaluations_participating_in=[evaluation, already_evaluated], evaluations_voted_for=[already_evaluated])

        page = self.app.get(reverse('staff:user_edit', args=[student.pk]), user='manager', status=200)
        form = page.forms['user-form']
        form['evaluations_participating_in'] = [already_evaluated.pk]

        page = form.submit().follow()
        # fetch the user name, which became lowercased
        student.refresh_from_db()

        self.assertIn("Successfully updated user.", page)
        self.assertIn("The removal of evaluations has granted the user &quot;{}&quot; 3 reward points for the active semester.".format(student.username), page)


class TestUserMergeSelectionView(WebTestWith200Check):
    url = "/staff/user/merge"
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        mommy.make(UserProfile)


class TestUserMergeView(WebTestWith200Check):
    url = "/staff/user/3/merge/4"
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        mommy.make(UserProfile, pk=3)
        mommy.make(UserProfile, pk=4)


class TestUserBulkDeleteView(WebTest):
    url = '/staff/user/bulk_delete'
    filename = os.path.join(settings.BASE_DIR, 'staff/fixtures/test_user_bulk_delete_file.txt')

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_testrun_deletes_no_users(self):
        page = self.app.get(self.url, user='manager')
        form = page.forms['user-bulk-delete-form']

        form['username_file'] = (self.filename,)

        mommy.make(UserProfile, is_active=False)
        users_before = UserProfile.objects.count()

        reply = form.submit(name='operation', value='test')

        # Not getting redirected after.
        self.assertEqual(reply.status_code, 200)
        # No user got deleted.
        self.assertEqual(users_before, UserProfile.objects.count())

    def test_deletes_users(self):
        mommy.make(UserProfile, username='testuser1')
        mommy.make(UserProfile, username='testuser2')
        contribution1 = mommy.make(Contribution)
        semester = mommy.make(Semester, participations_are_archived=True)
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=semester), _participant_count=0, _voter_count=0)
        contribution2 = mommy.make(Contribution, evaluation=evaluation)
        mommy.make(UserProfile, username='contributor1', contributions=[contribution1])
        mommy.make(UserProfile, username='contributor2', contributions=[contribution2])

        page = self.app.get(self.url, user='manager')
        form = page.forms["user-bulk-delete-form"]

        form["username_file"] = (self.filename,)

        user_count_before = UserProfile.objects.count()

        reply = form.submit(name="operation", value="bulk_delete")

        # Getting redirected after.
        self.assertEqual(reply.status_code, 302)

        # Assert only one user got deleted and one was marked inactive
        self.assertTrue(UserProfile.objects.filter(username='testuser1').exists())
        self.assertFalse(UserProfile.objects.filter(username='testuser2').exists())
        self.assertTrue(UserProfile.objects.filter(username='manager').exists())

        self.assertTrue(UserProfile.objects.filter(username='contributor1').exists())
        self.assertTrue(UserProfile.objects.exclude_inactive_users().filter(username='contributor1').exists())
        self.assertTrue(UserProfile.objects.filter(username='contributor2').exists())
        self.assertFalse(UserProfile.objects.exclude_inactive_users().filter(username='contributor2').exists())

        self.assertEqual(UserProfile.objects.count(), user_count_before - 1)
        self.assertEqual(UserProfile.objects.exclude_inactive_users().count(), user_count_before - 2)


class TestUserImportView(WebTest):
    url = "/staff/user/import"
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls")
    filename_invalid = os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls")
    filename_random = os.path.join(settings.BASE_DIR, "staff/fixtures/random.random")

    @classmethod
    def setUpTestData(cls):
        cls.user = mommy.make(UserProfile, username="manager", groups=[Group.objects.get(name="Manager")])

    def test_success_handling(self):
        """
        Tests whether a correct excel file is correctly tested and imported and whether the success messages are displayed
        """
        page = self.app.get(self.url, user='manager')
        form = page.forms["user-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test")

        self.assertContains(page, 'The import run will create 2 user(s):<br>Lucilia Manilium (lucilia.manilium)<br>Bastius Quid (bastius.quid.ext)')
        self.assertContains(page, 'Import previously uploaded file')

        form = page.forms["user-import-form"]
        form.submit(name="operation", value="import")

        page = self.app.get(self.url, user='manager')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_error_handling(self):
        """
        Tests whether errors given from the importer are displayed
        """
        page = self.app.get(self.url, user='manager')

        original_user_count = UserProfile.objects.count()

        form = page.forms["user-import-form"]
        form["excel_file"] = (self.filename_invalid,)

        reply = form.submit(name="operation", value="test")

        self.assertContains(reply, 'Sheet &quot;Sheet1&quot;, row 2: Email address is missing.')
        self.assertContains(reply, 'Errors occurred while parsing the input data. No data was imported.')
        self.assertNotContains(reply, 'Import previously uploaded file')

        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_warning_handling(self):
        """
        Tests whether warnings given from the importer are displayed
        """
        mommy.make(UserProfile, email="42@42.de", username="lucilia.manilium")

        page = self.app.get(self.url, user='manager')

        form = page.forms["user-import-form"]
        form["excel_file"] = (self.filename_valid,)

        reply = form.submit(name="operation", value="test")
        self.assertContains(reply, "The existing user would be overwritten with the following data:<br>"
                " - lucilia.manilium ( None None, 42@42.de) (existing)<br>"
                " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)")

        helper_delete_all_import_files(self.user.id)

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["user-import-form"]
        form["excel_file"] = (self.filename_valid,)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_invalid_upload_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["user-import-form"]
        page = form.submit(name="operation", value="test")

        self.assertContains(page, 'Please select an Excel file')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_invalid_import_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["user-import-form"]
        reply = form.submit(name="operation", value="import", expect_errors=True)

        self.assertEqual(reply.status_code, 400)


# Staff - Semester Views
class TestSemesterView(WebTest):
    url = '/staff/semester/1'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, pk=1)
        cls.evaluation1 = mommy.make(Evaluation, name_de="A - Evaluation 1", name_en="B - Evaluation 1", course=mommy.make(Course, semester=cls.semester))
        cls.evaluation2 = mommy.make(Evaluation, name_de="B - Evaluation 2", name_en="A - Evaluation 2", course=mommy.make(Course, semester=cls.semester))

    def test_view_list_sorting(self):
        page = self.app.get(self.url, user='manager', extra_environ={'HTTP_ACCEPT_LANGUAGE': 'en'}).body.decode("utf-8")
        position_evaluation1 = page.find("Evaluation 1")
        position_evaluation2 = page.find("Evaluation 2")
        self.assertGreater(position_evaluation1, position_evaluation2)

        page = self.app.get(self.url, user='manager', extra_environ={'HTTP_ACCEPT_LANGUAGE': 'de'}).body.decode("utf-8")
        position_evaluation1 = page.find("Evaluation 1")
        position_evaluation2 = page.find("Evaluation 2")
        self.assertLess(position_evaluation1, position_evaluation2)

    def test_access_to_semester_with_archived_results(self):
        mommy.make(UserProfile, username='reviewer', groups=[Group.objects.get(name='Reviewer')])
        mommy.make(Semester, pk=2, results_are_archived=True)

        # reviewers shouldn't be allowed to access the semester page
        self.app.get('/staff/semester/2', user='reviewer', status=403)

        # managers can access the page
        self.app.get('/staff/semester/2', user='manager', status=200)


class TestGetEvaluationsWithPrefetchedData(TestCase):
    def test_get_evaluations_with_prefetched_data(self):
        evaluation = mommy.make(Evaluation, is_single_result=True)
        get_evaluations_with_prefetched_data(evaluation.course.semester)


class TestSemesterCreateView(WebTest):
    url = '/staff/semester/create'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_create(self):
        name_de = 'name_de'
        short_name_de = 'short_name_de'
        name_en = 'name_en'
        short_name_en = 'short_name_en'

        response = self.app.get(self.url, user='manager')
        form = response.forms['semester-form']
        form['name_de'] = name_de
        form['short_name_de'] = short_name_de
        form['name_en'] = name_en
        form['short_name_en'] = short_name_en
        form.submit()

        self.assertEqual(Semester.objects.filter(name_de=name_de, name_en=name_en, short_name_de=short_name_de, short_name_en=short_name_en).count(), 1)


class TestSemesterEditView(WebTest):
    url = '/staff/semester/1/edit'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, pk=1, name_de='old_name', name_en='old_name')

    def test_name_change(self):
        new_name_de = 'new_name_de'
        new_name_en = 'new_name_en'
        self.assertNotEqual(self.semester.name_de, new_name_de)
        self.assertNotEqual(self.semester.name_en, new_name_en)

        response = self.app.get(self.url, user='manager')
        form = response.forms['semester-form']
        form['name_de'] = new_name_de
        form['name_en'] = new_name_en
        form.submit()

        self.semester.refresh_from_db()
        self.assertEqual(self.semester.name_de, new_name_de)
        self.assertEqual(self.semester.name_en, new_name_en)


class TestSemesterDeleteView(WebTest):
    url = '/staff/semester/delete'
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_failure(self):
        semester = mommy.make(Semester)
        mommy.make(Evaluation, course=mommy.make(Course, semester=semester), state='in_evaluation', voters=[mommy.make(UserProfile)])
        self.assertFalse(semester.can_manager_delete)
        response = self.app.post(self.url, params={'semester_id': semester.pk}, user='manager', expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Semester.objects.filter(pk=semester.pk).exists())

    def test_success(self):
        semester = mommy.make(Semester)
        self.assertTrue(semester.can_manager_delete)
        response = self.app.post(self.url, params={'semester_id': semester.pk}, user='manager')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Semester.objects.filter(pk=semester.pk).exists())


class TestSemesterAssignView(WebTest):
    url = '/staff/semester/1/assign'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, pk=1)
        lecture_type = mommy.make(CourseType, name_de="Vorlesung", name_en="Lecture")
        seminar_type = mommy.make(CourseType, name_de="Seminar", name_en="Seminar")
        cls.questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        evaluation1 = mommy.make(Evaluation, course=mommy.make(Course, semester=cls.semester, type=seminar_type))
        mommy.make(Contribution, contributor=mommy.make(UserProfile), evaluation=evaluation1,
                   responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        evaluation2 = mommy.make(Evaluation, course=mommy.make(Course, semester=cls.semester, type=lecture_type))
        mommy.make(Contribution, contributor=mommy.make(UserProfile), evaluation=evaluation2,
                   responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)

    def test_assign_questionnaires(self):
        page = self.app.get(self.url, user="manager")
        assign_form = page.forms["questionnaire-assign-form"]
        assign_form['Seminar'] = [self.questionnaire.pk]
        assign_form['Lecture'] = [self.questionnaire.pk]
        page = assign_form.submit().follow()

        for evaluation in self.semester.evaluations.all():
            self.assertEqual(evaluation.general_contribution.questionnaires.count(), 1)
            self.assertEqual(evaluation.general_contribution.questionnaires.get(), self.questionnaire)


class TestSemesterTodoView(WebTestWith200Check):
    url = '/staff/semester/1/todo'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, pk=1)

    def test_todo(self):
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=self.semester), state='prepared', name_en='name_to_find', name_de='name_to_find')
        user = mommy.make(UserProfile, username='user_to_find')
        mommy.make(Contribution, evaluation=evaluation, contributor=user, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)

        response = self.app.get(self.url, user='manager')
        self.assertContains(response, 'user_to_find')
        self.assertContains(response, 'name_to_find')


class TestSendReminderView(WebTest):
    url = '/staff/semester/1/responsible/3/send_reminder'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, pk=1)
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=cls.semester), state='prepared')
        responsible = mommy.make(UserProfile, pk=3, email='a.b@example.com')
        mommy.make(Contribution, evaluation=evaluation, contributor=responsible, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)

    def test_form(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["send-reminder-form"]
        form["body"] = "uiae"
        form.submit()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("uiae", mail.outbox[0].body)


class TestSemesterImportView(WebTest):
    url = "/staff/semester/1/import"
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/test_enrollment_data.xls")
    filename_invalid = os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_enrollment_data.xls")
    filename_random = os.path.join(settings.BASE_DIR, "staff/fixtures/random.random")

    @classmethod
    def setUpTestData(cls):
        mommy.make(Semester, pk=1)
        mommy.make(UserProfile, username="manager", groups=[Group.objects.get(name="Manager")])

    def test_import_valid_file(self):
        mommy.make(CourseType, name_de="Vorlesung", name_en="Vorlesung")
        mommy.make(CourseType, name_de="Seminar", name_en="Seminar")

        original_user_count = UserProfile.objects.count()

        page = self.app.get(self.url, user='manager')

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test")

        self.assertEqual(UserProfile.objects.count(), original_user_count)

        form = page.forms["semester-import-form"]
        form['vote_start_datetime'] = "2000-01-01 00:00:00"
        form['vote_end_date'] = "2012-01-01"
        form.submit(name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 23)

        evaluations = Evaluation.objects.all()
        self.assertEqual(len(evaluations), 23)

        for evaluation in evaluations:
            responsibles_count = Contribution.objects.filter(evaluation=evaluation, responsible=True).count()
            self.assertEqual(responsibles_count, 1)

        check_student = UserProfile.objects.get(username="diam.synephebos")
        self.assertEqual(check_student.first_name, "Diam")
        self.assertEqual(check_student.email, "diam.synephebos@institution.example.com")

        check_contributor = UserProfile.objects.get(username="sanctus.aliquyam.ext")
        self.assertEqual(check_contributor.first_name, "Sanctus")
        self.assertEqual(check_contributor.last_name, "Aliquyam")
        self.assertEqual(check_contributor.email, "567@external.example.com")

    def test_error_handling(self):
        """
        Tests whether errors given from the importer are displayed
        """
        page = self.app.get(self.url, user='manager')

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_invalid,)

        reply = form.submit(name="operation", value="test")
        self.assertContains(reply, 'Sheet &quot;MA Belegungen&quot;, row 3: The users&#39;s data (email: bastius.quid@external.example.com) differs from it&#39;s data in a previous row.')
        self.assertContains(reply, 'Sheet &quot;MA Belegungen&quot;, row 7: Email address is missing.')
        self.assertContains(reply, 'Sheet &quot;MA Belegungen&quot;, row 10: Email address is missing.')
        self.assertContains(reply, 'The imported data contains two email addresses with the same username')
        self.assertContains(reply, 'Errors occurred while parsing the input data. No data was imported.')

        self.assertNotContains(reply, 'Import previously uploaded file')

    def test_warning_handling(self):
        """
        Tests whether warnings given from the importer are displayed
        """
        mommy.make(UserProfile, email="42@42.de", username="lucilia.manilium")

        page = self.app.get(self.url, user='manager')

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_valid,)

        reply = form.submit(name="operation", value="test")
        self.assertContains(reply, "The existing user would be overwritten with the following data:<br>"
                " - lucilia.manilium ( None None, 42@42.de) (existing)<br>"
                " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)")

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_valid,)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_invalid_upload_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["semester-import-form"]
        page = form.submit(name="operation", value="test")

        self.assertContains(page, 'Please select an Excel file')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_invalid_import_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["semester-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        reply = form.submit(name="operation", value="import", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_missing_evaluation_period(self):
        mommy.make(CourseType, name_de="Vorlesung", name_en="Vorlesung")
        mommy.make(CourseType, name_de="Seminar", name_en="Seminar")

        page = self.app.get(self.url, user='manager')

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test")

        form = page.forms["semester-import-form"]
        page = form.submit(name="operation", value="import")

        self.assertContains(page, 'Please enter an evaluation period')
        self.assertContains(page, 'Import previously uploaded file')


class TestSemesterExportView(WebTest):
    url = '/staff/semester/1/export'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, pk=1)
        cls.course_type = mommy.make(CourseType)
        cls.evaluation = mommy.make(Evaluation, course=mommy.make(Course, type=cls.course_type, semester=cls.semester))

    def test_view_downloads_excel_file(self):
        page = self.app.get(self.url, user='manager')
        form = page.forms["semester-export-form"]

        # Check one course type.
        form.set('form-0-selected_course_types', 'id_form-0-selected_course_types_0')

        response = form.submit()

        # Load response as Excel file and check its heading for correctness.
        workbook = xlrd.open_workbook(file_contents=response.content)
        self.assertEqual(workbook.sheets()[0].row_values(0)[0],
                         'Evaluation {0}\n\n{1}'.format(self.semester.name, ", ".join([self.course_type.name])))


class TestSemesterRawDataExportView(WebTestWith200Check):
    url = '/staff/semester/1/raw_export'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, pk=1)
        cls.course_type = mommy.make(CourseType, name_en="Type")

    def test_view_downloads_csv_file(self):
        student_user = mommy.make(UserProfile, username='student')
        mommy.make(Evaluation, course=mommy.make(Course, type=self.course_type, semester=self.semester), participants=[student_user],
            voters=[student_user], name_de="1", name_en="Evaluation 1")
        mommy.make(Evaluation, course=mommy.make(Course, type=self.course_type, semester=self.semester), participants=[student_user],
            name_de="2", name_en="Evaluation 2")

        response = self.app.get(self.url, user='manager')
        expected_content = (
            "Name;Degrees;Type;Single result;State;#Voters;#Participants;#Text answers;Average grade\n"
            "Evaluation 1;;Type;False;new;1;1;0;\n"
            "Evaluation 2;;Type;False;new;0;1;0;\n"
        )
        self.assertEqual(response.content, expected_content.encode("utf-8"))

    def test_single_result(self):
        mommy.make(Evaluation, course=mommy.make(Course, type=self.course_type, semester=self.semester), _participant_count=5, _voter_count=5,
            is_single_result=True, name_de="3", name_en="Single Result")

        response = self.app.get(self.url, user='manager')
        expected_content = (
            "Name;Degrees;Type;Single result;State;#Voters;#Participants;#Text answers;Average grade\n"
            "Single Result;;Type;True;new;5;5;0;\n"
        )
        self.assertEqual(response.content, expected_content.encode("utf-8"))


class TestSemesterParticipationDataExportView(WebTest):
    url = '/staff/semester/1/participation_export'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.student_user = mommy.make(UserProfile, username='student')
        cls.student_user2 = mommy.make(UserProfile, username='student2')
        cls.semester = mommy.make(Semester, pk=1)
        cls.course_type = mommy.make(CourseType, name_en="Type")
        cls.evaluation1 = mommy.make(Evaluation, course=mommy.make(Course, type=cls.course_type, semester=cls.semester), participants=[cls.student_user],
            voters=[cls.student_user], name_de="Veranstaltung 1", name_en="Evaluation 1", is_rewarded=True)
        cls.evaluation2 = mommy.make(Evaluation, course=mommy.make(Course, type=cls.course_type, semester=cls.semester), participants=[cls.student_user, cls.student_user2],
            name_de="Veranstaltung 2", name_en="Evaluation 2", is_rewarded=False)
        mommy.make(Contribution, evaluation=cls.evaluation1, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        mommy.make(Contribution, evaluation=cls.evaluation2, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        mommy.make(RewardPointGranting, semester=cls.semester, user_profile=cls.student_user, value=23)
        mommy.make(RewardPointGranting, semester=cls.semester, user_profile=cls.student_user, value=42)

    def test_view_downloads_csv_file(self):
        response = self.app.get(self.url, user='manager')
        expected_content = (
            "Username;Can use reward points;#Required evaluations voted for;#Required evaluations;#Optional evaluations voted for;"
            "#Optional evaluations;Earned reward points\n"
            "student;False;1;1;0;1;65\n"
            "student2;False;0;0;0;1;0\n")
        self.assertEqual(response.content, expected_content.encode("utf-8"))


class TestLoginKeyExportView(WebTest):
    url = '/staff/semester/1/evaluation/1/login_key_export'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

        cls.external_user = mommy.make(UserProfile, email="user@external.com")
        cls.internal_user = mommy.make(UserProfile, email="user@institution.example.com")

        semester = mommy.make(Semester, pk=1)
        mommy.make(Evaluation, pk=1, course=mommy.make(Course, semester=semester), participants=[cls.external_user, cls.internal_user], voters=[cls.external_user, cls.internal_user])

    def test_login_key_export_works_as_expected(self):
        self.assertEqual(self.external_user.login_key, None)
        self.assertEqual(self.internal_user.login_key, None)

        response = self.app.get(self.url, user='manager')

        self.external_user.refresh_from_db()
        self.assertNotEqual(self.external_user.login_key, None)
        self.assertEqual(self.internal_user.login_key, None)

        expected_string = "Last name;First name;Email;Login key\n;;user@external.com;localhost:8000/key/{}\n".format(self.external_user.login_key)
        self.assertEqual(response.body.decode(), expected_string)


class TestEvaluationOperationView(WebTest):
    url = '/staff/semester/1/evaluationoperation'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, pk=1)

    def helper_semester_state_views(self, evaluation, old_state, new_state):
        page = self.app.get("/staff/semester/1", user="manager")
        form = page.forms["evaluation_operation_form"]
        self.assertIn(evaluation.state, old_state)
        form['evaluation'] = evaluation.pk
        response = form.submit('target_state', value=new_state)

        form = response.forms["evaluation-operation-form"]
        response = form.submit()
        self.assertIn("Successfully", str(response))
        self.assertEqual(Evaluation.objects.get(pk=evaluation.pk).state, new_state)

    """
        The following tests make sure the evaluation state transitions are triggerable via the UI.
    """
    def test_semester_publish(self):
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=self.semester), state='reviewed')
        self.helper_semester_state_views(evaluation, "reviewed", "published")

    def test_semester_reset_1(self):
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=self.semester), state='prepared')
        self.helper_semester_state_views(evaluation, "prepared", "new")

    def test_semester_reset_2(self):
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=self.semester), state='approved')
        self.helper_semester_state_views(evaluation, "approved", "new")

    def test_semester_contributor_ready_1(self):
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=self.semester), state='new')
        self.helper_semester_state_views(evaluation, "new", "prepared")

    def test_semester_contributor_ready_2(self):
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=self.semester), state='editor_approved')
        self.helper_semester_state_views(evaluation, "editor_approved", "prepared")

    def test_semester_unpublish(self):
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=self.semester), state='published', _participant_count=0, _voter_count=0)
        self.helper_semester_state_views(evaluation, "published", "reviewed")

    def test_operation_start_evaluation(self):
        evaluation = mommy.make(Evaluation, state='approved', course=mommy.make(Course, semester=self.semester))
        urloptions = '?evaluation={}&target_state=in_evaluation'.format(evaluation.pk)

        response = self.app.get(self.url + urloptions, user='manager')
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "manager"'.format(self.url))

        form = response.forms['evaluation-operation-form']
        form.submit()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'in_evaluation')

    def test_operation_prepare(self):
        evaluation = mommy.make(Evaluation, state='new', course=mommy.make(Course, semester=self.semester))
        urloptions = '?evaluation={}&target_state=prepared'.format(evaluation.pk)

        response = self.app.get(self.url + urloptions, user='manager')
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "manager"'.format(self.url))

        form = response.forms['evaluation-operation-form']
        form.submit()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'prepared')


class TestSingleResultCreateView(WebTest):
    url = '/staff/semester/1/singleresult/create'

    @classmethod
    def setUpTestData(cls):
        cls.manager_user = mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        mommy.make(Semester, pk=1)
        cls.course_type = mommy.make(CourseType)
        cls.degree = mommy.make(Degree)

    def test_single_result_create(self):
        """
            Tests the single result creation view with one valid and one invalid input dataset.
        """
        response = self.app.get(self.url, user="manager", status=200)
        form = response.forms["single-result-form"]
        form["name_de"] = "qwertz"
        form["name_en"] = "qwertz"
        form["type"] = self.course_type.pk
        form["degrees"] = [self.degree.pk]
        form["event_date"] = "2014-01-01"
        form["answer_1"] = 6
        form["answer_3"] = 2
        # missing responsible to get a validation error

        form.submit()
        self.assertFalse(Evaluation.objects.exists())

        form["responsible"] = self.manager_user.pk  # now do it right

        form.submit()
        self.assertEqual(Evaluation.objects.get().name_de, "qwertz")


# Staff - Semester - Evaluation Views
class TestEvaluationCreateView(WebTest):
    url = '/staff/semester/1/evaluation/create'

    @classmethod
    def setUpTestData(cls):
        cls.manager_user = mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        mommy.make(Semester, pk=1)
        cls.course_type = mommy.make(CourseType)
        cls.q1 = mommy.make(Questionnaire, type=Questionnaire.TOP)
        cls.q2 = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)

    def test_evaluation_create(self):
        """
            Tests the evaluation creation view with one valid and one invalid input dataset.
        """
        response = self.app.get(self.url, user="manager", status=200)
        form = response.forms["evaluation-form"]
        form["course-name_de"] = "lfo9e7bmxp1xi"
        form["course-name_en"] = "asdf"
        form["name_de"] = "lfo9e7bmxp1xi"
        form["name_en"] = "asdf"
        form["course-type"] = self.course_type.pk
        form["course-degrees"] = [1]
        form["vote_start_datetime"] = "2099-01-01 00:00:00"
        form["vote_end_date"] = "2014-01-01"  # wrong order to get the validation error
        form["general_questionnaires"] = [self.q1.pk]

        form['contributions-TOTAL_FORMS'] = 1
        form['contributions-INITIAL_FORMS'] = 0
        form['contributions-MAX_NUM_FORMS'] = 5
        form['contributions-0-evaluation'] = ''
        form['contributions-0-contributor'] = self.manager_user.pk
        form['contributions-0-questionnaires'] = [self.q2.pk]
        form['contributions-0-order'] = 0
        form['contributions-0-responsibility'] = Contribution.IS_RESPONSIBLE
        form['contributions-0-textanswer_visibility'] = Contribution.GENERAL_TEXTANSWERS

        form.submit()
        self.assertFalse(Evaluation.objects.exists())

        form["vote_start_datetime"] = "2014-01-01 00:00:00"
        form["vote_end_date"] = "2099-01-01"  # now do it right

        form.submit()
        self.assertEqual(Evaluation.objects.get().name_de, "lfo9e7bmxp1xi")


@override_settings(REWARD_POINTS=[
    (1 / 3, 1),
    (2 / 3, 2),
    (3 / 3, 3),
])
class TestEvaluationEditView(WebTest):
    url = '/staff/semester/1/evaluation/1/edit'

    @classmethod
    def setUpTestData(cls):
        cls.user = mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        semester = mommy.make(Semester, pk=1)
        degree = mommy.make(Degree)
        cls.evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=semester, degrees=[degree]), pk=1, last_modified_user=cls.user,
            vote_start_datetime=datetime.datetime(2099, 1, 1, 0, 0), vote_end_date=datetime.date(2099, 12, 31))
        mommy.make(Questionnaire, questions=[mommy.make(Question)])
        cls.evaluation.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        # This is necessary so that the call to is_single_result does not fail.
        responsible = mommy.make(UserProfile)
        cls.contribution = mommy.make(Contribution, evaluation=cls.evaluation, contributor=responsible, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)

    def setUp(self):
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)

    def test_edit_evaluation(self):
        user = mommy.make(UserProfile)
        page = self.app.get(self.url, user="manager")

        # remove responsibility
        form = page.forms["evaluation-form"]
        form['contributions-0-contributor'] = user.pk
        form['contributions-0-responsibility'] = Contribution.IS_RESPONSIBLE
        form.submit("operation", value="save")
        self.assertEqual(list(self.evaluation.responsible_contributors), [user])

    def test_remove_responsibility(self):
        page = self.app.get(self.url, user="manager")

        # remove responsibility
        form = page.forms["evaluation-form"]
        form['contributions-0-responsibility'] = "CONTRIBUTOR"
        page = form.submit("operation", value="save")

        self.assertIn("No responsible contributors found", page)

    def test_participant_removal_reward_point_granting_message(self):
        already_evaluated = mommy.make(Evaluation, course=mommy.make(Course, semester=self.evaluation.course.semester))
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        other = mommy.make(UserProfile, evaluations_participating_in=[self.evaluation])
        student = mommy.make(UserProfile, email="foo@institution.example.com",
            evaluations_participating_in=[self.evaluation, already_evaluated], evaluations_voted_for=[already_evaluated])

        page = self.app.get(self.url, user='manager')

        # remove a single participant
        form = page.forms['evaluation-form']
        form['participants'] = [other.pk]
        page = form.submit('operation', value='save').follow()

        self.assertIn("The removal as participant has granted the user &quot;{}&quot; 3 reward points for the semester.".format(student.username), page)

    def test_remove_participants(self):
        already_evaluated = mommy.make(Evaluation, course=mommy.make(Course, semester=self.evaluation.course.semester))
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        student = mommy.make(UserProfile, evaluations_participating_in=[self.evaluation])

        for name in ["a", "b", "c", "d", "e"]:
            mommy.make(UserProfile, username=name, email="{}@institution.example.com".format(name),
                evaluations_participating_in=[self.evaluation, already_evaluated], evaluations_voted_for=[already_evaluated])

        page = self.app.get(self.url, user='manager')

        # remove five participants
        form = page.forms['evaluation-form']
        form['participants'] = [student.pk]
        page = form.submit('operation', value='save').follow()

        for name in ["a", "b", "c", "d", "e"]:
            self.assertIn("The removal as participant has granted the user &quot;{}&quot; 3 reward points for the semester.".format(name), page)

    def test_remove_participants_proportional_reward_points(self):
        already_evaluated = mommy.make(Evaluation, course=mommy.make(Course, semester=self.evaluation.course.semester))
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        student = mommy.make(UserProfile, evaluations_participating_in=[self.evaluation])

        for name, points_granted in [("a", 0), ("b", 1), ("c", 2), ("d", 3)]:
            user = mommy.make(UserProfile, username=name, email="{}@institution.example.com".format(name),
                evaluations_participating_in=[self.evaluation, already_evaluated], evaluations_voted_for=[already_evaluated])
            RewardPointGranting.objects.create(user_profile=user, semester=self.evaluation.course.semester, value=points_granted)

        page = self.app.get(self.url, user='manager')

        # remove four participants
        form = page.forms['evaluation-form']
        form['participants'] = [student.pk]
        page = form.submit('operation', value='save').follow()

        self.assertIn("The removal as participant has granted the user &quot;a&quot; 3 reward points for the semester.", page)
        self.assertIn("The removal as participant has granted the user &quot;b&quot; 2 reward points for the semester.", page)
        self.assertIn("The removal as participant has granted the user &quot;c&quot; 1 reward point for the semester.", page)
        self.assertNotIn("The removal as participant has granted the user &quot;d&quot;", page)

    def test_last_modified_user(self):
        """
            Tests whether the button "Save and approve" does only change the
            last_modified_user if changes were made.
        """
        test_user = mommy.make(UserProfile, username='approve_test_user', groups=[Group.objects.get(name='Manager')])

        old_name_de = self.evaluation.name_de
        old_vote_start_datetime = self.evaluation.vote_start_datetime
        old_vote_end_date = self.evaluation.vote_end_date
        old_last_modified_user = self.evaluation.last_modified_user
        old_state = self.evaluation.state
        self.assertEqual(old_last_modified_user.username, self.user.username)
        self.assertEqual(old_state, "new")

        page = self.app.get(self.url, user=test_user.username, status=200)
        form = page.forms["evaluation-form"]
        # approve without changes
        form.submit(name="operation", value="approve")

        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.last_modified_user, old_last_modified_user)  # the last_modified_user should not have changed
        self.assertEqual(self.evaluation.state, "approved")
        self.assertEqual(self.evaluation.name_de, old_name_de)
        self.assertEqual(self.evaluation.vote_start_datetime, old_vote_start_datetime)
        self.assertEqual(self.evaluation.vote_end_date, old_vote_end_date)

        self.evaluation.revert_to_new()
        self.evaluation.save()
        self.assertEqual(self.evaluation.state, "new")

        page = self.app.get(self.url, user=test_user.username, status=200)
        form = page.forms["evaluation-form"]
        form["name_de"] = "Test name"
        # approve after changes
        form.submit(name="operation", value="approve")

        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.last_modified_user, test_user)  # the last_modified_user should have changed
        self.assertEqual(self.evaluation.state, "approved")
        self.assertEqual(self.evaluation.name_de, "Test name")  # the name should have changed
        self.assertEqual(self.evaluation.vote_start_datetime, old_vote_start_datetime)
        self.assertEqual(self.evaluation.vote_end_date, old_vote_end_date)

    def test_last_modified_on_formset_change(self):
        """
            Tests if last_modified_{user,time} is updated if only the contributor formset is changed
        """

        self.assertEqual(self.evaluation.last_modified_user, self.user)
        last_modified_time_before = self.evaluation.last_modified_time

        test_user = mommy.make(
            UserProfile,
            username='approve_test_user',
            groups=[Group.objects.get(name='Manager')]
        )
        page = self.app.get(self.url, user=test_user.username, status=200)
        form = page.forms["evaluation-form"]

        # Change label of the first contribution
        form['contributions-0-label'] = 'test_label'
        form.submit(name="operation", value="approve")

        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.state, 'approved')
        self.assertEqual(self.evaluation.last_modified_user, test_user)
        self.assertGreater(self.evaluation.last_modified_time, last_modified_time_before)

    def test_last_modified_unchanged(self):
        """
            Tests if last_modified_{user,time} stays the same when no values are changed in the form
        """
        last_modified_user_before = self.evaluation.last_modified_user
        last_modified_time_before = self.evaluation.last_modified_time

        test_user = mommy.make(
            UserProfile,
            username='approve_test_user',
            groups=[Group.objects.get(name='Manager')]
        )

        page = self.app.get(self.url, user=test_user, status=200)
        form = page.forms["evaluation-form"]
        form.submit(name="operation", value="approve")

        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.state, 'approved')
        self.assertEqual(self.evaluation.last_modified_user, last_modified_user_before)
        self.assertEqual(self.evaluation.last_modified_time, last_modified_time_before)


class TestSingleResultEditView(WebTestWith200Check):
    url = '/staff/semester/1/evaluation/1/edit'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        semester = mommy.make(Semester, pk=1)

        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=semester), pk=1)
        responsible = mommy.make(UserProfile)
        contribution = mommy.make(Contribution, evaluation=evaluation, contributor=responsible, responsible=True, can_edit=True,
                                  textanswer_visibility=Contribution.GENERAL_TEXTANSWERS, questionnaires=[Questionnaire.single_result_questionnaire()])

        question = Questionnaire.single_result_questionnaire().questions.get()
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution, answer=1, count=5)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution, answer=2, count=15)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution, answer=3, count=40)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution, answer=4, count=60)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution, answer=5, count=30)


class TestEvaluationPreviewView(WebTestWith200Check):
    url = '/staff/semester/1/evaluation/1/preview'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        semester = mommy.make(Semester, pk=1)
        evaluation = mommy.make(Evaluation, course=mommy.make(Course, semester=semester), pk=1)
        evaluation.general_contribution.questionnaires.set([mommy.make(Questionnaire)])


class TestEvaluationImportPersonsView(WebTest):
    url = "/staff/semester/1/evaluation/1/person_management"
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls")
    filename_invalid = os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls")
    filename_random = os.path.join(settings.BASE_DIR, "staff/fixtures/random.random")

    @classmethod
    def setUpTestData(cls):
        semester = mommy.make(Semester, pk=1)
        cls.manager_user = mommy.make(UserProfile, username="manager", groups=[Group.objects.get(name="Manager")])
        cls.evaluation = mommy.make(Evaluation, pk=1, course=mommy.make(Course, semester=semester))
        profiles = mommy.make(UserProfile, _quantity=42)
        cls.evaluation2 = mommy.make(Evaluation, pk=2, course=mommy.make(Course, semester=semester), participants=profiles)

    @classmethod
    def tearDown(cls):
        # delete the uploaded file again so other tests can start with no file guaranteed
        helper_delete_all_import_files(cls.manager_user.id)

    def test_import_valid_participants_file(self):
        page = self.app.get(self.url, user='manager')

        original_participant_count = self.evaluation.participants.count()

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test-participants")

        self.assertContains(page, 'Import previously uploaded file')
        self.assertEqual(self.evaluation.participants.count(), original_participant_count)

        form = page.forms["participant-import-form"]
        form.submit(name="operation", value="import-participants")
        self.assertEqual(self.evaluation.participants.count(), original_participant_count + 2)

        page = self.app.get(self.url, user='manager')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_copy_participants(self):
        page = self.app.get(self.url, user='manager')

        original_participant_count = self.evaluation.participants.count()

        form = page.forms["participant-copy-form"]
        form["evaluation"] = str(self.evaluation2.pk)
        page = form.submit(name="operation", value="copy-participants")

        self.assertEqual(self.evaluation.participants.count(), original_participant_count + self.evaluation2.participants.count())

    def test_import_valid_contributors_file(self):
        page = self.app.get(self.url, user='manager')

        original_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()

        form = page.forms["contributor-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test-contributors")

        self.assertContains(page, 'Import previously uploaded file')
        self.assertEqual(UserProfile.objects.filter(contributions__evaluation=self.evaluation).count(), original_contributor_count)

        form = page.forms["contributor-import-form"]
        form.submit(name="operation", value="import-contributors")
        self.assertEqual(UserProfile.objects.filter(contributions__evaluation=self.evaluation).count(), original_contributor_count + 2)

        page = self.app.get(self.url, user='manager')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_copy_contributors(self):
        page = self.app.get(self.url, user='manager')

        original_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()

        form = page.forms["contributor-copy-form"]
        form["evaluation"] = str(self.evaluation2.pk)
        page = form.submit(name="operation", value="copy-contributors")

        new_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()
        self.assertEqual(new_contributor_count, original_contributor_count + UserProfile.objects.filter(contributions__evaluation=self.evaluation2).count())

    def test_import_participants_error_handling(self):
        """
        Tests whether errors given from the importer are displayed
        """
        page = self.app.get(self.url, user='manager')

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_invalid,)

        reply = form.submit(name="operation", value="test-participants")

        self.assertContains(reply, 'Sheet &quot;Sheet1&quot;, row 2: Email address is missing.')
        self.assertContains(reply, 'Errors occurred while parsing the input data. No data was imported.')
        self.assertNotContains(reply, 'Import previously uploaded file')

    def test_import_participants_warning_handling(self):
        """
        Tests whether warnings given from the importer are displayed
        """
        mommy.make(UserProfile, email="42@42.de", username="lucilia.manilium")

        page = self.app.get(self.url, user='manager')

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)

        reply = form.submit(name="operation", value="test-participants")
        self.assertContains(reply, "The existing user would be overwritten with the following data:<br>"
                " - lucilia.manilium ( None None, 42@42.de) (existing)<br>"
                " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)")

    def test_import_contributors_error_handling(self):
        """
        Tests whether errors given from the importer are displayed
        """
        page = self.app.get(self.url, user='manager')

        form = page.forms["contributor-import-form"]
        form["excel_file"] = (self.filename_invalid,)

        reply = form.submit(name="operation", value="test-contributors")

        self.assertContains(reply, 'Sheet &quot;Sheet1&quot;, row 2: Email address is missing.')
        self.assertContains(reply, 'Errors occurred while parsing the input data. No data was imported.')
        self.assertNotContains(reply, 'Import previously uploaded file')

    def test_import_contributors_warning_handling(self):
        """
        Tests whether warnings given from the importer are displayed
        """
        mommy.make(UserProfile, email="42@42.de", username="lucilia.manilium")

        page = self.app.get(self.url, user='manager')

        form = page.forms["contributor-import-form"]
        form["excel_file"] = (self.filename_valid,)

        reply = form.submit(name="operation", value="test-contributors")
        self.assertContains(reply, "The existing user would be overwritten with the following data:<br>"
                " - lucilia.manilium ( None None, 42@42.de) (existing)<br>"
                " - lucilia.manilium ( Lucilia Manilium, lucilia.manilium@institution.example.com) (new)")

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_invalid_contributor_upload_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["contributor-import-form"]
        page = form.submit(name="operation", value="test-contributors")

        self.assertContains(page, 'Please select an Excel file')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_invalid_participant_upload_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["participant-import-form"]
        page = form.submit(name="operation", value="test-participants")

        self.assertContains(page, 'Please select an Excel file')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_invalid_contributor_import_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["contributor-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        reply = form.submit(name="operation", value="import-contributors", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_invalid_participant_import_operation(self):
        page = self.app.get(self.url, user='manager')

        form = page.forms["participant-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        reply = form.submit(name="operation", value="import-participants", expect_errors=True)

        self.assertEqual(reply.status_code, 400)


class TestEvaluationEmailView(WebTest):
    url = '/staff/semester/1/evaluation/1/email'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        semester = mommy.make(Semester, pk=1)
        participant1 = mommy.make(UserProfile, email="foo@example.com")
        participant2 = mommy.make(UserProfile, email="bar@example.com")
        mommy.make(Evaluation, pk=1, course=mommy.make(Course, semester=semester), participants=[participant1, participant2])

    def test_emails_are_sent(self):
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["evaluation-email-form"]
        form.get("recipients", index=0).checked = True  # send to all participants
        form["subject"] = "asdf"
        form["body"] = "asdf"
        form.submit()

        self.assertEqual(len(mail.outbox), 2)


class TestEvaluationTextAnswerView(WebTest):
    url = '/staff/semester/1/evaluation/1/textanswers'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        semester = mommy.make(Semester, pk=1)
        student1 = mommy.make(UserProfile)
        cls.student2 = mommy.make(UserProfile)
        cls.evaluation = mommy.make(Evaluation, pk=1, course=mommy.make(Course, semester=semester), participants=[student1, cls.student2], voters=[student1], state="in_evaluation")
        top_general_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        mommy.make(Question, questionnaire=top_general_questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])
        questionnaire = mommy.make(Questionnaire)
        question = mommy.make(Question, questionnaire=questionnaire, type=Question.TEXT)
        contribution = mommy.make(Contribution, evaluation=cls.evaluation, contributor=mommy.make(UserProfile), questionnaires=[questionnaire])
        cls.answer = 'should show up'
        mommy.make(TextAnswer, contribution=contribution, question=question, answer=cls.answer)

    def test_textanswers_showing_up(self):
        # in an evaluation with only one voter the view should not be available
        self.app.get(self.url, user='manager', status=403)

        # add additional voter
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)

        # now it should work
        self.app.get(self.url, user='manager', status=200)

    def test_textanswers_quick_view(self):
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)
        page = self.app.get(self.url, user='manager', status=200)
        self.assertContains(page, self.answer)

    def test_textanswers_full_view(self):
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)
        page = self.app.get(self.url + '?view=full', user='manager', status=200)
        self.assertContains(page, self.answer)


class TestEvaluationTextAnswerEditView(WebTest):
    url = '/staff/semester/1/evaluation/1/textanswer/00000000-0000-0000-0000-000000000001/edit'

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        semester = mommy.make(Semester, pk=1)
        student1 = mommy.make(UserProfile)
        cls.student2 = mommy.make(UserProfile)
        cls.evaluation = mommy.make(Evaluation, pk=1, course=mommy.make(Course, semester=semester), participants=[student1, cls.student2], voters=[student1], state="in_evaluation")
        top_general_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        mommy.make(Question, questionnaire=top_general_questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])
        questionnaire = mommy.make(Questionnaire)
        question = mommy.make(Question, questionnaire=questionnaire, type=Question.TEXT)
        contribution = mommy.make(Contribution, evaluation=cls.evaluation, contributor=mommy.make(UserProfile), questionnaires=[questionnaire])
        mommy.make(TextAnswer, contribution=contribution, question=question, answer='test answer text', pk='00000000-0000-0000-0000-000000000001')

    def test_textanswers_showing_up(self):
        # in an evaluation with only one voter the view should not be available
        self.app.get(self.url, user='manager', status=403)

        # add additional voter
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)

        # now it should work
        response = self.app.get(self.url, user='manager')

        form = response.forms['textanswer-edit-form']
        self.assertEqual(form['answer'].value, 'test answer text')
        form['answer'] = 'edited answer text'
        form.submit()

        answer = TextAnswer.objects.get(pk='00000000-0000-0000-0000-000000000001')
        self.assertEqual(answer.answer, 'edited answer text')


# Staff Questionnaire Views
class TestQuestionnaireNewVersionView(WebTest):
    url = '/staff/questionnaire/2/new_version'

    @classmethod
    def setUpTestData(cls):
        cls.name_de_orig = 'kurzer name'
        cls.name_en_orig = 'short name'
        questionnaire = mommy.make(Questionnaire, id=2, name_de=cls.name_de_orig, name_en=cls.name_en_orig)
        mommy.make(Question, questionnaire=questionnaire)
        mommy.make(UserProfile, username="manager", groups=[Group.objects.get(name="Manager")])

    def test_changes_old_title(self):
        page = self.app.get(url=self.url, user='manager')
        form = page.forms['questionnaire-form']

        form.submit()

        timestamp = datetime.date.today()
        new_name_de = '{} (until {})'.format(self.name_de_orig, str(timestamp))
        new_name_en = '{} (until {})'.format(self.name_en_orig, str(timestamp))

        self.assertTrue(Questionnaire.objects.filter(name_de=self.name_de_orig, name_en=self.name_en_orig).exists())
        self.assertTrue(Questionnaire.objects.filter(name_de=new_name_de, name_en=new_name_en).exists())

    def test_no_second_update(self):
        # First save.
        page = self.app.get(url=self.url, user='manager')
        form = page.forms['questionnaire-form']
        form.submit()

        # Second try.
        new_questionnaire = Questionnaire.objects.get(name_de=self.name_de_orig)
        page = self.app.get(url='/staff/questionnaire/{}/new_version'.format(new_questionnaire.id), user='manager')

        # We should get redirected back to the questionnaire index.
        self.assertEqual(page.status_code, 302)  # REDIRECT
        self.assertEqual(page.location, '/staff/questionnaire/')


class TestQuestionnaireCreateView(WebTest):
    url = "/staff/questionnaire/create"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_create_questionnaire(self):
        page = self.app.get(self.url, user="manager")

        questionnaire_form = page.forms["questionnaire-form"]
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire"
        questionnaire_form['questions-0-text_de'] = "Frage 1"
        questionnaire_form['questions-0-text_en'] = "Question 1"
        questionnaire_form['questions-0-type'] = Question.TEXT
        questionnaire_form['order'] = 0
        questionnaire_form['type'] = Questionnaire.TOP
        questionnaire_form.submit().follow()

        # retrieve new questionnaire
        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
        self.assertEqual(questionnaire.questions.count(), 1)

    def test_create_empty_questionnaire(self):
        page = self.app.get(self.url, user="manager")

        questionnaire_form = page.forms["questionnaire-form"]
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire"
        questionnaire_form['order'] = 0
        page = questionnaire_form.submit()

        self.assertIn("You must have at least one of these", page)

        self.assertFalse(Questionnaire.objects.filter(name_de="Test Fragebogen", name_en="test questionnaire").exists())


class TestQuestionnaireIndexView(WebTest):
    url = "/staff/questionnaire/"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.contributor_questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)
        cls.top_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        cls.bottom_questionnaire = mommy.make(Questionnaire, type=Questionnaire.BOTTOM)

    def test_ordering(self):
        content = self.app.get(self.url, user="manager").body.decode()
        top_index = content.index(self.top_questionnaire.name)
        contributor_index = content.index(self.contributor_questionnaire.name)
        bottom_index = content.index(self.bottom_questionnaire.name)

        self.assertTrue(top_index < contributor_index < bottom_index)


class TestQuestionnaireEditView(WebTestWith200Check):
    url = '/staff/questionnaire/2/edit'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        evaluation = mommy.make(Evaluation, state='in_evaluation')
        cls.questionnaire = mommy.make(Questionnaire, id=2)
        mommy.make(Contribution, questionnaires=[cls.questionnaire], evaluation=evaluation)

        mommy.make(Question, questionnaire=cls.questionnaire)
        mommy.make(UserProfile, username="manager", groups=[Group.objects.get(name="Manager")])

    def test_allowed_type_changes_on_used_questionnaire(self):
        # top to bottom
        self.questionnaire.type = Questionnaire.TOP
        self.questionnaire.save()

        page = self.app.get(self.url, user='manager')
        form = page.forms['questionnaire-form']
        self.assertEqual(form['type'].options, [('10', True, 'Top questionnaire'), ('30', False, 'Bottom questionnaire')])

        # bottom to top
        self.questionnaire.type = Questionnaire.BOTTOM
        self.questionnaire.save()

        page = self.app.get(self.url, user='manager')
        form = page.forms['questionnaire-form']
        self.assertEqual(form['type'].options, [('10', False, 'Top questionnaire'), ('30', True, 'Bottom questionnaire')])

        # contributor has no other possible type
        self.questionnaire.type = Questionnaire.CONTRIBUTOR
        self.questionnaire.save()

        page = self.app.get(self.url, user='manager')
        form = page.forms['questionnaire-form']
        self.assertEqual(form['type'].options, [('20', True, 'Contributor questionnaire')])


class TestQuestionnaireViewView(WebTestWith200Check):
    url = '/staff/questionnaire/2'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        questionnaire = mommy.make(Questionnaire, id=2)
        mommy.make(Question, questionnaire=questionnaire, type=Question.TEXT)
        mommy.make(Question, questionnaire=questionnaire, type=Question.GRADE)
        mommy.make(Question, questionnaire=questionnaire, type=Question.LIKERT)
        mommy.make(UserProfile, username="manager", groups=[Group.objects.get(name="Manager")])


class TestQuestionnaireCopyView(WebTest):
    url = '/staff/questionnaire/2/copy'

    @classmethod
    def setUpTestData(cls):
        questionnaire = mommy.make(Questionnaire, id=2)
        mommy.make(Question, questionnaire=questionnaire)
        mommy.make(UserProfile, username="manager", groups=[Group.objects.get(name="Manager")])

    def test_not_changing_name_fails(self):
        response = self.app.get(self.url, user="manager", status=200)
        response = response.forms[1].submit("", status=200)
        self.assertIn("already exists", response)

    def test_copy_questionnaire(self):
        page = self.app.get(self.url, user="manager")

        questionnaire_form = page.forms["questionnaire-form"]
        questionnaire_form['name_de'] = "Test Fragebogen (kopiert)"
        questionnaire_form['name_en'] = "test questionnaire (copied)"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen (kopiert)"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire (copied)"
        page = questionnaire_form.submit().follow()

        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen (kopiert)", name_en="test questionnaire (copied)")
        self.assertEqual(questionnaire.questions.count(), 1)


class TestQuestionnaireDeletionView(WebTest):
    url = "/staff/questionnaire/delete"
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.q1 = mommy.make(Questionnaire)
        cls.q2 = mommy.make(Questionnaire)
        mommy.make(Contribution, questionnaires=[cls.q1])

    def test_questionnaire_deletion(self):
        """
            Tries to delete two questionnaires via the respective post request,
            only the second attempt should succeed.
        """
        self.assertFalse(Questionnaire.objects.get(pk=self.q1.pk).can_manager_delete)
        response = self.app.post("/staff/questionnaire/delete", params={"questionnaire_id": self.q1.pk}, user="manager", expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Questionnaire.objects.filter(pk=self.q1.pk).exists())

        self.assertTrue(Questionnaire.objects.get(pk=self.q2.pk).can_manager_delete)
        response = self.app.post("/staff/questionnaire/delete", params={"questionnaire_id": self.q2.pk}, user="manager")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Questionnaire.objects.filter(pk=self.q2.pk).exists())


# Staff Course Types Views
class TestCourseTypeView(WebTest):
    url = "/staff/course_types/"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_page_displays_something(self):
        CourseType.objects.create(name_de='uZJcsl0rNc', name_en='uZJcsl0rNc')
        page = self.app.get(self.url, user="manager", status=200)
        self.assertIn('uZJcsl0rNc', page)

    def test_course_type_form(self):
        """
            Adds a course type via the staff form and verifies that the type was created in the db.
        """
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["course-type-form"]
        last_form_id = int(form["form-TOTAL_FORMS"].value) - 1
        form["form-" + str(last_form_id) + "-name_de"].value = "Test"
        form["form-" + str(last_form_id) + "-name_en"].value = "Test"
        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertTrue(CourseType.objects.filter(name_de="Test", name_en="Test").exists())


class TestCourseTypeMergeSelectionView(WebTest):
    url = "/staff/course_types/merge"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.main_type = mommy.make(CourseType, name_en="A course type")
        cls.other_type = mommy.make(CourseType, name_en="Obsolete course type")

    def test_same_evaluation_fails(self):
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["course-type-merge-selection-form"]
        form["main_type"] = self.main_type.pk
        form["other_type"] = self.main_type.pk
        response = form.submit()
        self.assertIn("You must select two different course types", str(response))


class TestCourseTypeMergeView(WebTest):
    url = "/staff/course_types/1/merge/2"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.main_type = mommy.make(CourseType, pk=1, name_en="A course type")
        cls.other_type = mommy.make(CourseType, pk=2, name_en="Obsolete course type")
        mommy.make(Course, type=cls.main_type)
        mommy.make(Course, type=cls.other_type)

    def test_merge_works(self):
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["course-type-merge-form"]
        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertFalse(CourseType.objects.filter(name_en="Obsolete course type").exists())
        self.assertEqual(Course.objects.filter(type=self.main_type).count(), 2)
        for course in Course.objects.all():
            self.assertTrue(course.type == self.main_type)


# Other Views
class TestEvaluationTextAnswersUpdatePublishView(WebTest):
    url = reverse("staff:evaluation_textanswers_update_publish")
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="manager.user", groups=[Group.objects.get(name="Manager")])
        cls.student1 = mommy.make(UserProfile)
        cls.student2 = mommy.make(UserProfile)
        cls.evaluation = mommy.make(Evaluation, participants=[cls.student1, cls.student2], voters=[cls.student1], state="in_evaluation")
        top_general_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        mommy.make(Question, questionnaire=top_general_questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])

    def helper(self, old_state, expected_new_state, action, expect_errors=False):
        textanswer = mommy.make(TextAnswer, state=old_state)
        response = self.app.post(self.url, params={"id": textanswer.id, "action": action, "evaluation_id": self.evaluation.pk}, user="manager.user", expect_errors=expect_errors)
        if expect_errors:
            self.assertEqual(response.status_code, 403)
        else:
            self.assertEqual(response.status_code, 200)
            textanswer.refresh_from_db()
            self.assertEqual(textanswer.state, expected_new_state)

    def test_review_actions(self):
        # in an evaluation with only one voter reviewing should fail
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PUBLISHED, "publish", expect_errors=True)

        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)

        # now reviewing should work
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PUBLISHED, "publish")
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.HIDDEN, "hide")
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PRIVATE, "make_private")
        self.helper(TextAnswer.PUBLISHED, TextAnswer.NOT_REVIEWED, "unreview")


class ParticipationArchivingTests(WebTest):

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="manager", groups=[Group.objects.get(name="Manager")])

    def test_raise_403(self):
        """
            Tests whether inaccessible views on semesters/evaluations with archived participations correctly raise a 403.
        """
        semester = mommy.make(Semester, participations_are_archived=True)

        semester_url = "/staff/semester/{}/".format(semester.pk)

        self.app.get(semester_url + "import", user="manager", status=403)
        self.app.get(semester_url + "assign", user="manager", status=403)
        self.app.get(semester_url + "evaluation/create", user="manager", status=403)
        self.app.get(semester_url + "evaluationoperation", user="manager", status=403)


class TestTemplateEditView(WebTest):
    url = "/staff/template/1"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_emailtemplate(self):
        """
            Tests the emailtemplate view with one valid and one invalid input datasets.
        """
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["template-form"]
        form["subject"] = "subject: mflkd862xmnbo5"
        form["body"] = "body: mflkd862xmnbo5"
        form.submit()

        self.assertEqual(EmailTemplate.objects.get(pk=1).body, "body: mflkd862xmnbo5")

        form["body"] = " invalid tag: {{}}"
        form.submit()
        self.assertEqual(EmailTemplate.objects.get(pk=1).body, "body: mflkd862xmnbo5")


class TestDegreeView(WebTest):
    url = "/staff/degrees/"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])

    def test_degree_form(self):
        """
            Adds a degree via the staff form and verifies that the degree was created in the db.
        """
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["degree-form"]
        last_form_id = int(form["form-TOTAL_FORMS"].value) - 1
        form["form-" + str(last_form_id) + "-name_de"].value = "Test"
        form["form-" + str(last_form_id) + "-name_en"].value = "Test"
        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertTrue(Degree.objects.filter(name_de="Test", name_en="Test").exists())


class TestSemesterQuestionnaireAssignment(WebTest):
    url = "/staff/semester/1/assign"

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        cls.semester = mommy.make(Semester, id=1)
        cls.course_type_1 = mommy.make(CourseType)
        cls.course_type_2 = mommy.make(CourseType)
        cls.responsible = mommy.make(UserProfile)
        cls.questionnaire_1 = mommy.make(Questionnaire, type=Questionnaire.TOP)
        cls.questionnaire_2 = mommy.make(Questionnaire, type=Questionnaire.TOP)
        cls.questionnaire_responsible = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)
        cls.evaluation_1 = mommy.make(Evaluation, course=mommy.make(Course, semester=cls.semester, type=cls.course_type_1))
        cls.evaluation_2 = mommy.make(Evaluation, course=mommy.make(Course, semester=cls.semester, type=cls.course_type_2))
        mommy.make(Contribution, contributor=cls.responsible, evaluation=cls.evaluation_1, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        mommy.make(Contribution, contributor=cls.responsible, evaluation=cls.evaluation_2, responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)

    def test_questionnaire_assignment(self):
        page = self.app.get(self.url, user="manager", status=200)
        form = page.forms["questionnaire-assign-form"]
        form[self.course_type_1.name] = [self.questionnaire_1.pk, self.questionnaire_2.pk]
        form[self.course_type_2.name] = [self.questionnaire_2.pk]
        form["Responsible contributor"] = [self.questionnaire_responsible.pk]

        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertEqual(set(self.evaluation_1.general_contribution.questionnaires.all()), set([self.questionnaire_1, self.questionnaire_2]))
        self.assertEqual(set(self.evaluation_2.general_contribution.questionnaires.all()), set([self.questionnaire_2]))
        self.assertEqual(set(self.evaluation_1.contributions.get(contributor=self.responsible).questionnaires.all()), set([self.questionnaire_responsible]))
        self.assertEqual(set(self.evaluation_2.contributions.get(contributor=self.responsible).questionnaires.all()), set([self.questionnaire_responsible]))
