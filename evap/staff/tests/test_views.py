import datetime
import os
from unittest.mock import patch, PropertyMock

from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse
from django.test import override_settings
from django.test.testcases import TestCase

from django_webtest import WebTest
from model_bakery import baker
import xlrd

from evap.evaluation.models import (Contribution, Course, CourseType, Degree, EmailTemplate, Evaluation, FaqSection,
                                    FaqQuestion, Question, Questionnaire, RatingAnswerCounter, Semester, TextAnswer,
                                    UserProfile)
from evap.evaluation.tests.tools import FuzzyInt, let_user_vote_for_evaluation, WebTestWith200Check, make_manager
from evap.rewards.models import SemesterActivation, RewardPointGranting
from evap.staff.tools import generate_import_filename, ImportType
from evap.staff.forms import ContributionCopyForm, ContributionCopyFormSet, EvaluationCopyForm
from evap.staff.views import get_evaluations_with_prefetched_data


def helper_delete_all_import_files(user_id):
    for import_type in ImportType:
        filename = generate_import_filename(user_id, import_type)
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass


class TestDownloadSampleXlsView(WebTest):
    url = '/staff/download_sample_xls/sample.xls'
    email_placeholder = "institution.com"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_sample_file_correctness(self):
        page = self.app.get(self.url, user=self.manager)

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


class TestStaffIndexView(WebTestWith200Check):
    url = '/staff/'

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]


class TestStaffFAQView(WebTestWith200Check):
    url = '/staff/faq/'

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]


class TestStaffFAQEditView(WebTestWith200Check):
    url = '/staff/faq/1'

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]

        section = baker.make(FaqSection, pk=1)
        baker.make(FaqQuestion, section=section)


class TestUserIndexView(WebTest):
    url = '/staff/user/'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_num_queries_is_constant(self):
        """
            ensures that the number of queries in the user list is constant
            and not linear to the number of users
        """
        num_users = 50
        semester = baker.make(Semester, participations_are_archived=True)

        # this triggers more checks in UserProfile.can_be_deleted_by_manager
        evaluation = baker.make(
            Evaluation,
            state="published",
            course__semester=semester,
            _participant_count=1,
            _voter_count=1,
        )
        baker.make(UserProfile, _quantity=num_users, evaluations_participating_in=[evaluation])

        with self.assertNumQueries(FuzzyInt(0, num_users - 1)):
            self.app.get(self.url, user=self.manager)


class TestUserCreateView(WebTest):
    url = "/staff/user/create"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_user_is_created(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["user-form"]
        form["first_name"] = "asd"
        form["last_name"] = "asd"
        form["email"] = "a@b.de"

        form.submit()

        self.assertEqual(UserProfile.objects.order_by("pk").last().email, "a@b.de")


@override_settings(REWARD_POINTS=[
    (1 / 3, 1),
    (2 / 3, 2),
    (3 / 3, 3),
])
class TestUserEditView(WebTest):
    url = "/staff/user/3/edit"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        baker.make(UserProfile, pk=3)

    def test_questionnaire_edit(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["user-form"]
        form["email"] = "lfo9e7bmxp1xi@institution.example.com"
        form.submit()
        self.assertTrue(UserProfile.objects.filter(email='lfo9e7bmxp1xi@institution.example.com').exists())

    def test_reward_points_granting_message(self):
        evaluation = baker.make(Evaluation, course__semester__is_active=True)
        already_evaluated = baker.make(Evaluation, course=baker.make(Course, semester=evaluation.course.semester))
        SemesterActivation.objects.create(semester=evaluation.course.semester, is_active=True)
        student = baker.make(UserProfile, email="foo@institution.example.com",
            evaluations_participating_in=[evaluation, already_evaluated], evaluations_voted_for=[already_evaluated])

        page = self.app.get(reverse('staff:user_edit', args=[student.pk]), user=self.manager, status=200)
        form = page.forms['user-form']
        form['evaluations_participating_in'] = [already_evaluated.pk]

        page = form.submit().follow()
        # fetch the user name, which became lowercased
        student.refresh_from_db()

        self.assertIn("Successfully updated user.", page)
        self.assertIn("The removal of evaluations has granted the user &quot;{}&quot; 3 reward points for the active semester.".format(student.email), page)


class TestUserMergeSelectionView(WebTestWith200Check):
    url = "/staff/user/merge"

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]

        baker.make(UserProfile)


class TestUserMergeView(WebTestWith200Check):
    url = "/staff/user/3/merge/4"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.test_users = [cls.manager]

        cls.main_user = baker.make(UserProfile, pk=3)
        cls.other_user = baker.make(UserProfile, pk=4)

    def test_shows_evaluations_participating_in(self):
        evaluation = baker.make(Evaluation, name_en="The journey of unit-testing", participants=[self.main_user])

        page = self.app.get(self.url, user=self.manager)
        self.assertContains(page, evaluation.name_en, count=2,
                            msg_prefix="The evaluation name should be displayed twice: "
                                       "in the column of the participant and in the column of the merged data")

    def test_shows_evaluations_voted_for(self):
        evaluation = baker.make(Evaluation, name_en="Voting theory", voters=[self.main_user])

        page = self.app.get(self.url, user=self.manager)
        self.assertContains(page, evaluation.name_en, count=2,
                            msg_prefix="The evaluation name should be displayed twice: "
                                       "in the column of the voter and in the column of the merged data")


class TestUserBulkUpdateView(WebTest):
    url = '/staff/user/bulk_update'
    filename = os.path.join(settings.BASE_DIR, 'staff/fixtures/test_user_bulk_update_file.txt')
    filename_random = os.path.join(settings.BASE_DIR, 'staff/fixtures/random.random')
    filename_xls = os.path.join(settings.BASE_DIR, 'staff/fixtures/test_enrollment_data.xls')

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_testrun_deletes_no_users(self):
        page = self.app.get(self.url, user=self.manager)
        form = page.forms['user-bulk-update-form']

        form['user_file'] = (self.filename,)

        baker.make(UserProfile, is_active=False)
        users_before = set(UserProfile.objects.all())

        reply = form.submit(name='operation', value='test')

        self.assertEqual(reply.status_code, 200)
        # No user got deleted.
        self.assertEqual(users_before, set(UserProfile.objects.all()))

        helper_delete_all_import_files(self.manager.id)

    @override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.example.com", "internal.example.com"])
    def test_multiple_email_matches_trigger_error(self):
        baker.make(UserProfile, email='testremove@institution.example.com')
        baker.make(UserProfile, first_name="Elisabeth", last_name="Fröhlich", email='testuser1@institution.example.com')

        error_string = (
            'Multiple users match the email testuser1@institution.example.com:'
            + '<br />Elisabeth Fröhlich (testuser1@institution.example.com)'
            + '<br />Tony Kuchenbuch (testuser1@internal.example.com)'
        )
        button_substring = 'value="bulk_update"'

        expected_users = set(UserProfile.objects.all())

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-bulk-update-form"]
        form["user_file"] = (self.filename,)
        response = form.submit(name="operation", value="test")

        self.assertIn(button_substring, response)
        self.assertNotIn(error_string, response)
        self.assertEqual(set(UserProfile.objects.all()), expected_users)

        new_user = baker.make(UserProfile, first_name="Tony", last_name="Kuchenbuch", email='testuser1@internal.example.com')
        expected_users.add(new_user)

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-bulk-update-form"]
        form["user_file"] = (self.filename,)
        response = form.submit(name="operation", value="test")

        self.assertNotIn(button_substring, response)
        self.assertIn(error_string, response)
        self.assertEqual(set(UserProfile.objects.all()), expected_users)

    @override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.example.com", "internal.example.com"])
    def test_handles_users(self):
        baker.make(UserProfile, email='testuser1@institution.example.com')
        baker.make(UserProfile, email='testuser2@institution.example.com')
        baker.make(UserProfile, email='testupdate@institution.example.com')
        contribution1 = baker.make(Contribution)
        semester = baker.make(Semester, participations_are_archived=True)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, semester=semester),
            _participant_count=0,
            _voter_count=0,
        )
        contribution2 = baker.make(Contribution, evaluation=evaluation)
        baker.make(UserProfile, email='contributor1@institution.example.com', contributions=[contribution1])
        baker.make(UserProfile, email='contributor2@institution.example.com', contributions=[contribution2])

        expected_users = set(UserProfile.objects.exclude(email='testuser2@institution.example.com'))

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-bulk-update-form"]
        form["user_file"] = (self.filename,)
        response = form.submit(name="operation", value="test")

        self.assertIn(
            '1 will be updated, 1 will be deleted and 1 will be marked inactive. 1 new users will be created.',
            response
        )
        self.assertIn('testupdate@institution.example.com > testupdate@internal.example.com', response)

        form = response.forms["user-bulk-update-form"]
        response = form.submit(name="operation", value="bulk_update")

        # testuser1 is in the file and must not be deleted
        self.assertTrue(UserProfile.objects.filter(email='testuser1@institution.example.com').exists())
        # testuser2 is not in the file and must be deleted
        self.assertFalse(UserProfile.objects.filter(email='testuser2@institution.example.com').exists())
        # manager is not in the file but still must not be deleted
        self.assertTrue(UserProfile.objects.filter(email='manager@institution.example.com').exists())
        # testusernewinternal is a new internal user and should be created
        self.assertTrue(UserProfile.objects.filter(email='testusernewinternal@institution.example.com').exists())
        expected_users.add(UserProfile.objects.get(email='testusernewinternal@institution.example.com'))
        # testusernewexternal is an external user and should not be created
        self.assertFalse(UserProfile.objects.filter(email='testusernewexternal@example.com').exists())
        # testupdate should have been renamed
        self.assertFalse(UserProfile.objects.filter(email='testupdate@institution.example.com').exists())
        self.assertTrue(UserProfile.objects.filter(email='testupdate@internal.example.com').exists())

        # contributor1 should still be active, contributor2 should have been set to inactive
        self.assertTrue(UserProfile.objects.get(email='contributor1@institution.example.com').is_active)
        self.assertFalse(UserProfile.objects.get(email='contributor2@institution.example.com').is_active)
        # all should be active except for contributor2
        self.assertEqual(UserProfile.objects.filter(is_active=True).count(), len(expected_users) - 1)

        self.assertEqual(set(UserProfile.objects.all()), expected_users)

    @override_settings(DEBUG=False)
    def test_wrong_files_dont_crash(self):
        page = self.app.get(self.url, user=self.manager)
        form = page.forms['user-bulk-update-form']
        form['user_file'] = (self.filename_random,)
        reply = form.submit(name='operation', value='test')
        self.assertEqual(reply.status_code, 200)
        self.assertIn("An error happened when processing the file", reply)

        page = self.app.get(self.url, user=self.manager)
        form = page.forms['user-bulk-update-form']
        form['user_file'] = (self.filename_xls,)
        reply = form.submit(name='operation', value='test')
        self.assertEqual(reply.status_code, 200)
        self.assertIn("An error happened when processing the file", reply)


class TestUserImportView(WebTest):
    url = "/staff/user/import"
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls")
    filename_invalid = os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls")
    filename_random = os.path.join(settings.BASE_DIR, "staff/fixtures/random.random")

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_success_handling(self):
        """
        Tests whether a correct excel file is correctly tested and imported and whether the success messages are displayed
        """
        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test")

        self.assertContains(page, 'The import run will create 2 users:<br />Lucilia Manilium (lucilia.manilium@institution.example.com)<br />Bastius Quid (bastius.quid@external.example.com)')
        self.assertContains(page, 'Import previously uploaded file')

        form = page.forms["user-import-form"]
        form.submit(name="operation", value="import")

        page = self.app.get(self.url, user=self.manager)
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_error_handling(self):
        """
        Tests whether errors given from the importer are displayed
        """
        page = self.app.get(self.url, user=self.manager)

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
        baker.make(UserProfile, email="lucilia.manilium@institution.example.com")

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-import-form"]
        form["excel_file"] = (self.filename_valid,)

        reply = form.submit(name="operation", value="test")
        self.assertContains(reply, "The existing user would be overwritten with the following data:<br />"
                " -  None None, lucilia.manilium@institution.example.com (existing)<br />"
                " -  Lucilia Manilium, lucilia.manilium@institution.example.com (new)")

        helper_delete_all_import_files(self.manager.id)

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-import-form"]
        form["excel_file"] = (self.filename_valid,)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_invalid_upload_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-import-form"]
        page = form.submit(name="operation", value="test")

        self.assertContains(page, 'This field is required.')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_invalid_import_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-import-form"]
        reply = form.submit(name="operation", value="import", expect_errors=True)

        self.assertEqual(reply.status_code, 400)


# Staff - Semester Views
class TestSemesterView(WebTest):
    url = '/staff/semester/1'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1)
        cls.evaluation1 = baker.make(
            Evaluation,
            name_de="Evaluation 1",
            name_en="Evaluation 1",
            course=baker.make(Course, name_de="A", name_en="B", semester=cls.semester),
        )
        cls.evaluation2 = baker.make(
            Evaluation,
            name_de="Evaluation 2",
            name_en="Evaluation 2",
            course=baker.make(Course, name_de="B", name_en="A", semester=cls.semester),
        )

    def test_view_list_sorting(self):
        self.manager.language = 'en'
        self.manager.save()
        page = self.app.get(self.url, user=self.manager).body.decode("utf-8")
        position_evaluation1 = page.find("Evaluation 1")
        position_evaluation2 = page.find("Evaluation 2")
        self.assertGreater(position_evaluation1, position_evaluation2)
        self.app.reset()  # language is only loaded on login, so we're forcing a re-login here

        self.manager.language = 'de'
        self.manager.save()
        page = self.app.get(self.url, user=self.manager).body.decode("utf-8")
        position_evaluation1 = page.find("Evaluation 1")
        position_evaluation2 = page.find("Evaluation 2")
        self.assertLess(position_evaluation1, position_evaluation2)

    def test_access_to_semester_with_archived_results(self):
        reviewer = baker.make(
            UserProfile,
            email='reviewer@institution.example.com',
            groups=[Group.objects.get(name='Reviewer')],
        )
        baker.make(Semester, pk=2, results_are_archived=True)

        # reviewers shouldn't be allowed to access the semester page
        self.app.get('/staff/semester/2', user=reviewer, status=403)

        # managers can access the page
        self.app.get('/staff/semester/2', user=self.manager, status=200)

    @override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com"])
    def test_badge_for_external_responsibles(self):
        responsible = baker.make(UserProfile, email='a@institution.com')
        course = baker.make(Course, semester=self.semester, responsibles=[responsible])
        baker.make(Evaluation, course=course)
        response = self.app.get(self.url, user=self.manager)
        self.assertNotContains(response, 'External responsible')

        responsible.email = 'r@external.com'
        responsible.save()
        response = self.app.get(self.url, user=self.manager)
        self.assertContains(response, 'External responsible')

    @patch("evap.evaluation.models.Evaluation.textanswer_review_state", new_callable=PropertyMock)
    def test_textanswer_review_state_tags(self, textanswer_review_state_mock):
        """ Regression test for #1465 """

        evaluation = baker.make(
            Evaluation,
            state="in_evaluation",
            can_publish_text_results=True,
            course__semester=self.semester,
        )
        baker.make(TextAnswer, contribution=evaluation.general_contribution)

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.NO_TEXTANSWERS
        page = self.app.get(f'/staff/semester/{evaluation.course.semester.id}', user=self.manager)
        expected_count = page.body.decode().count('no_textanswers')

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.REVIEW_NEEDED
        page = self.app.get(f'/staff/semester/{evaluation.course.semester.id}', user=self.manager)
        # + 1 because the buttons at the top of the page contain it two times (once for _urgent)
        self.assertEqual(page.body.decode().count('unreviewed_textanswers'), expected_count + 1)
        self.assertEqual(page.body.decode().count('no_textanswers'), 1)

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.REVIEW_URGENT
        page = self.app.get(f'/staff/semester/{evaluation.course.semester.id}', user=self.manager)
        self.assertEqual(page.body.decode().count('unreviewed_textanswers_urgent'), expected_count)
        self.assertEqual(page.body.decode().count('no_textanswers'), 1)

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.REVIEWED
        page = self.app.get(f'/staff/semester/{evaluation.course.semester.id}', user=self.manager)
        self.assertEqual(page.body.decode().count('textanswers_reviewed'), expected_count)
        self.assertEqual(page.body.decode().count('no_textanswers'), 1)


class TestGetEvaluationsWithPrefetchedData(TestCase):
    @staticmethod
    def test_get_evaluations_with_prefetched_data():
        evaluation = baker.make(Evaluation, is_single_result=True)
        get_evaluations_with_prefetched_data(evaluation.course.semester)


class TestSemesterCreateView(WebTest):
    url = '/staff/semester/create'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_create(self):
        name_de = 'name_de'
        short_name_de = 'short_name_de'
        name_en = 'name_en'
        short_name_en = 'short_name_en'

        response = self.app.get(self.url, user=self.manager)
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
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1, name_de='old_name', name_en='old_name')

    def test_name_change(self):
        new_name_de = 'new_name_de'
        new_name_en = 'new_name_en'
        self.assertNotEqual(self.semester.name_de, new_name_de)
        self.assertNotEqual(self.semester.name_en, new_name_en)

        response = self.app.get(self.url, user=self.manager)
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
        cls.manager = make_manager()

    def test_failure(self):
        semester = baker.make(Semester)
        baker.make(
            Evaluation,
            course=baker.make(Course, semester=semester),
            state='in_evaluation',
            voters=[baker.make(UserProfile)],
        )
        self.assertFalse(semester.can_be_deleted_by_manager)

        response = self.app.post(self.url, params={'semester_id': semester.pk}, user=self.manager, expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Semester.objects.filter(pk=semester.pk).exists())

    def test_success_if_no_courses(self):
        semester = baker.make(Semester)
        self.assertTrue(semester.can_be_deleted_by_manager)
        response = self.app.post(self.url, params={'semester_id': semester.pk}, user=self.manager)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Semester.objects.filter(pk=semester.pk).exists())

    def test_success_if_archived(self):
        semester = baker.make(Semester)
        course = baker.make(Course, semester=semester)
        evaluation = baker.make(Evaluation, course=course, state='published')
        general_contribution = evaluation.general_contribution
        responsible_contribution = baker.make(Contribution, evaluation=evaluation, contributor=baker.make(UserProfile))
        textanswer = baker.make(TextAnswer, contribution=general_contribution, state='PU')
        ratinganswercounter = baker.make(RatingAnswerCounter, contribution=responsible_contribution)

        self.assertFalse(semester.can_be_deleted_by_manager)

        semester.archive_participations()
        semester.delete_grade_documents()
        semester.archive_results()

        self.assertTrue(semester.can_be_deleted_by_manager)
        response = self.app.post(self.url, params={'semester_id': semester.pk}, user=self.manager)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Semester.objects.filter(pk=semester.pk).exists())
        self.assertFalse(Course.objects.filter(pk=course.pk).exists())
        self.assertFalse(Evaluation.objects.filter(pk=evaluation.pk).exists())
        self.assertFalse(Contribution.objects.filter(pk=general_contribution.pk).exists())
        self.assertFalse(Contribution.objects.filter(pk=responsible_contribution.pk).exists())
        self.assertFalse(TextAnswer.objects.filter(pk=textanswer.pk).exists())
        self.assertFalse(RatingAnswerCounter.objects.filter(pk=ratinganswercounter.pk).exists())

    def test_failure_if_active(self):
        semester = baker.make(Semester, is_active=True)
        response = self.app.post(self.url, user=self.manager, expect_errors=True, params={
            "semester_id": semester.id,
        })
        self.assertEqual(response.status_code, 400)


class TestSemesterAssignView(WebTest):
    url = '/staff/semester/1/assign'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1)
        lecture_type = baker.make(CourseType, name_de="Vorlesung", name_en="Lecture")
        seminar_type = baker.make(CourseType, name_de="Seminar", name_en="Seminar")
        cls.questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)

        evaluation1 = baker.make(Evaluation, course__type=seminar_type, course__semester=cls.semester)
        baker.make(
            Contribution,
            contributor=baker.make(UserProfile),
            evaluation=evaluation1,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        evaluation2 = baker.make(Evaluation, course__type=lecture_type, course__semester=cls.semester)

        baker.make(
            Contribution,
            contributor=baker.make(UserProfile),
            evaluation=evaluation2,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )

    def test_assign_questionnaires(self):
        page = self.app.get(self.url, user=self.manager)
        assign_form = page.forms["questionnaire-assign-form"]
        assign_form['Seminar'] = [self.questionnaire.pk]
        assign_form['Lecture'] = [self.questionnaire.pk]
        page = assign_form.submit().follow()

        for evaluation in self.semester.evaluations.all():
            self.assertEqual(evaluation.general_contribution.questionnaires.count(), 1)
            self.assertEqual(evaluation.general_contribution.questionnaires.get(), self.questionnaire)


class TestSemesterPreparationReminderView(WebTestWith200Check):
    url = '/staff/semester/1/preparation_reminder'
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1)

        cls.test_users = [cls.manager]

    def test_preparation_reminder(self):
        user = baker.make(UserProfile, email='user_to_find@institution.example.com')
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, semester=self.semester, responsibles=[user]),
            state='prepared',
            name_en='name_to_find',
            name_de='name_to_find',
        )
        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=user,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )

        response = self.app.get(self.url, user=self.manager)
        self.assertContains(response, 'user_to_find')
        self.assertContains(response, 'name_to_find')

    @patch("evap.staff.views.EmailTemplate")
    def test_remind_all(self, email_template_mock):
        user = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, course=baker.make(Course, semester=self.semester, responsibles=[user]), state='prepared')

        email_template_mock.objects.get.return_value = email_template_mock
        email_template_mock.EDITOR_REVIEW_REMINDER = EmailTemplate.EDITOR_REVIEW_REMINDER

        response = self.app.post(self.url, user=self.manager)
        self.assertEqual(response.status_code, 200)

        subject_params = {}
        body_params = {"user": user, "evaluations": [evaluation]}
        expected = (user, subject_params, body_params)

        email_template_mock.send_to_user.assert_called_once()
        self.assertEqual(email_template_mock.send_to_user.call_args_list[0][0][:4], expected)


class TestSendReminderView(WebTest):
    url = '/staff/semester/1/responsible/3/send_reminder'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1)
        responsible = baker.make(UserProfile, pk=3, email='a.b@example.com')
        baker.make(
            Evaluation,
            course=baker.make(Course, semester=cls.semester, responsibles=[responsible]),
            state='prepared',
        )

    def test_form(self):
        page = self.app.get(self.url, user=self.manager)

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
        cls.manager = make_manager()
        baker.make(Semester, pk=1)
        baker.make(CourseType, name_de="Vorlesung", name_en="Lecture", import_names=["Vorlesung"])
        baker.make(CourseType, name_de="Seminar", name_en="Seminar", import_names=["Seminar"])

    def test_import_valid_file(self):
        original_user_count = UserProfile.objects.count()

        page = self.app.get(self.url, user=self.manager)

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
        self.assertEqual(Course.objects.count(), 23)

        for evaluation in evaluations:
            self.assertEqual(evaluation.course.responsibles.count(), 1)

        check_student = UserProfile.objects.get(email="diam.synephebos@institution.example.com")
        self.assertEqual(check_student.first_name, "Diam")

        check_contributor = UserProfile.objects.get(email="567@external.example.com")
        self.assertEqual(check_contributor.first_name, "Sanctus")
        self.assertEqual(check_contributor.last_name, "Aliquyam")

        check_course = Course.objects.get(name_en="Choose")
        self.assertEqual(check_course.name_de, "Wählen")
        self.assertEqual(check_course.responsibles.count(), 1)
        self.assertEqual(check_course.responsibles.first().full_name, "Prof. Dr. Sit Dolor")
        self.assertFalse(check_course.is_private)
        self.assertEqual(check_course.type.name_de, "Vorlesung")
        self.assertEqual(check_course.degrees.count(), 1)
        self.assertEqual(check_course.degrees.first().name_en, "Master")

        check_evaluation = check_course.evaluations.first()
        self.assertEqual(check_evaluation.name_en, "")
        self.assertEqual(check_evaluation.weight, 1)
        self.assertFalse(check_evaluation.is_single_result)
        self.assertTrue(check_evaluation.is_rewarded)
        self.assertFalse(check_evaluation.is_midterm_evaluation)
        self.assertEqual(check_evaluation.participants.count(), 2)
        self.assertFalse(check_evaluation.wait_for_grade_upload_before_publishing)

    def test_error_handling(self):
        """
        Tests whether errors given from the importer are displayed
        """
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_invalid,)

        reply = form.submit(name="operation", value="test")
        general_error = 'Errors occurred while parsing the input data. No data was imported.'
        self.assertContains(reply, general_error)
        degree_error = 'Error: No degree is associated with the import name &quot;Diploma&quot;. Please manually create it first.'
        self.assertContains(reply, degree_error)
        course_type_error = 'Error: No course type is associated with the import name &quot;Praktikum&quot;. Please manually create it first.'
        self.assertContains(reply, course_type_error)
        is_graded_error = '&quot;is_graded&quot; of course Deal is maybe, but must be yes or no'
        self.assertContains(reply, is_graded_error)
        user_error = 'Sheet &quot;MA Belegungen&quot;, row 3: The users&#x27;s data'\
                     ' (email: bastius.quid@external.example.com) differs from it&#x27;s data in a previous row.'
        self.assertContains(reply, user_error)
        self.assertContains(reply, 'Sheet &quot;MA Belegungen&quot;, row 7: Email address is missing.')
        self.assertContains(reply, 'Sheet &quot;MA Belegungen&quot;, row 10: Email address is missing.')

        def index(text):
            return reply.body.decode().index(text)

        self.assertTrue(index(general_error) < index(degree_error) < index(course_type_error) <
                        index(is_graded_error) < index(user_error))

        self.assertNotContains(reply, 'Import previously uploaded file')

    def test_warning_handling(self):
        """
        Tests whether warnings given from the importer are displayed
        """
        baker.make(UserProfile, email="lucilia.manilium@institution.example.com")

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_valid,)

        reply = form.submit(name="operation", value="test")
        self.assertContains(reply, "The existing user would be overwritten with the following data:<br />"
                " -  None None, lucilia.manilium@institution.example.com (existing)<br />"
                " -  Lucilia Manilium, lucilia.manilium@institution.example.com (new)")

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_valid,)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_invalid_upload_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        page = form.submit(name="operation", value="test")

        self.assertContains(page, 'This field is required.')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_invalid_import_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        reply = form.submit(name="operation", value="import", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_missing_evaluation_period(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test")

        form = page.forms["semester-import-form"]
        page = form.submit(name="operation", value="import")

        self.assertContains(page, 'This field is required.')
        self.assertContains(page, 'Import previously uploaded file')


class TestSemesterExportView(WebTest):
    url = '/staff/semester/1/export'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1)
        cls.degree = baker.make(Degree)
        cls.course_type = baker.make(CourseType)
        cls.evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, degrees=[cls.degree], type=cls.course_type, semester=cls.semester)
        )

    def test_view_downloads_excel_file(self):
        page = self.app.get(self.url, user=self.manager)
        form = page.forms["semester-export-form"]

        # Check one degree and course type.
        form.set('form-0-selected_degrees', 'id_form-0-selected_degrees_0')
        form.set('form-0-selected_course_types', 'id_form-0-selected_course_types_0')

        response = form.submit()

        # Load response as Excel file and check its heading for correctness.
        workbook = xlrd.open_workbook(file_contents=response.content)
        self.assertEqual(
            workbook.sheets()[0].row_values(0)[0],
            'Evaluation\n{}\n\n{}\n\n{}'.format(self.semester.name, self.degree.name, self.course_type.name)
        )


class TestSemesterRawDataExportView(WebTestWith200Check):
    url = '/staff/semester/1/raw_export'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1)
        cls.course_type = baker.make(CourseType, name_en="Type")

        cls.test_users = [cls.manager]

    def test_view_downloads_csv_file(self):
        student_user = baker.make(UserProfile, email='student@institution.example.com')
        baker.make(Evaluation, course=baker.make(Course, type=self.course_type, semester=self.semester, name_de="1",
            name_en="Course 1"), participants=[student_user], voters=[student_user], name_de="E1", name_en="E1")
        baker.make(Evaluation, course=baker.make(Course, type=self.course_type, semester=self.semester, name_de="2",
            name_en="Course 2"), participants=[student_user])

        response = self.app.get(self.url, user=self.manager)
        expected_content = (
            "Name;Degrees;Type;Single result;State;#Voters;#Participants;#Text answers;Average grade\n"
            "Course 1 – E1;;Type;False;new;1;1;0;\n"
            "Course 2;;Type;False;new;0;1;0;\n"
        )
        self.assertEqual(response.content, expected_content.encode("utf-8"))

    def test_single_result(self):
        baker.make(Evaluation, course=baker.make(Course, type=self.course_type, semester=self.semester, name_de="3",
            name_en="Single Result"), _participant_count=5, _voter_count=5, is_single_result=True)

        response = self.app.get(self.url, user=self.manager)
        expected_content = (
            "Name;Degrees;Type;Single result;State;#Voters;#Participants;#Text answers;Average grade\n"
            "Single Result;;Type;True;new;5;5;0;\n"
        )
        self.assertEqual(response.content, expected_content.encode("utf-8"))


class TestSemesterParticipationDataExportView(WebTest):
    url = '/staff/semester/1/participation_export'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.student_user = baker.make(UserProfile, email='student@example.com')
        cls.student_user2 = baker.make(UserProfile, email='student2@example.com')
        cls.semester = baker.make(Semester, pk=1)
        cls.course_type = baker.make(CourseType, name_en="Type")

        cls.evaluation1 = baker.make(
            Evaluation,
            course=baker.make(Course, type=cls.course_type, semester=cls.semester),
            participants=[cls.student_user],
            voters=[cls.student_user],
            name_de="Veranstaltung 1",
            name_en="Evaluation 1",
            is_rewarded=True,
        )
        cls.evaluation2 = baker.make(
            Evaluation,
            course=baker.make(Course, type=cls.course_type, semester=cls.semester),
            participants=[cls.student_user, cls.student_user2],
            name_de="Veranstaltung 2",
            name_en="Evaluation 2",
            is_rewarded=False,
        )
        baker.make(
            Contribution,
            evaluation=cls.evaluation1,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        baker.make(
            Contribution,
            evaluation=cls.evaluation2,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        baker.make(RewardPointGranting, semester=cls.semester, user_profile=cls.student_user, value=23)
        baker.make(RewardPointGranting, semester=cls.semester, user_profile=cls.student_user, value=42)

    def test_view_downloads_csv_file(self):
        response = self.app.get(self.url, user=self.manager)
        expected_content = (
            "Email;Can use reward points;#Required evaluations voted for;#Required evaluations;#Optional evaluations voted for;"
            "#Optional evaluations;Earned reward points\n"
            "student2@example.com;False;0;0;0;1;0\n"
            "student@example.com;False;1;1;0;1;65\n")
        self.assertEqual(response.content, expected_content.encode("utf-8"))


class TestLoginKeyExportView(WebTest):
    url = '/staff/semester/1/evaluation/1/login_key_export'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.external_user = baker.make(UserProfile, email="user@external.com")
        cls.internal_user = baker.make(UserProfile, email="user@institution.example.com")

        semester = baker.make(Semester, pk=1)
        baker.make(
            Evaluation,
            pk=1,
            course__semester=semester,
            participants=[cls.external_user, cls.internal_user],
            voters=[cls.external_user, cls.internal_user],
        )

    def test_login_key_export_works_as_expected(self):
        self.assertEqual(self.external_user.login_key, None)
        self.assertEqual(self.internal_user.login_key, None)

        response = self.app.get(self.url, user=self.manager)

        self.external_user.refresh_from_db()
        self.assertNotEqual(self.external_user.login_key, None)
        self.assertEqual(self.internal_user.login_key, None)

        expected_string = "Last name;First name;Email;Login key\n;;user@external.com;localhost:8000/key/{}\n".format(self.external_user.login_key)
        self.assertEqual(response.body.decode(), expected_string)


class TestEvaluationOperationView(WebTest):
    url = '/staff/semester/1/evaluationoperation'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1)
        cls.responsible = baker.make(UserProfile, email='responsible@example.com')
        cls.course = baker.make(Course, semester=cls.semester, responsibles=[cls.responsible])

    def helper_publish_evaluation_with_publish_notifications_for(self, evaluation, contributors=True, participants=True):
        page = self.app.get("/staff/semester/1", user=self.manager)
        form = page.forms["evaluation_operation_form"]
        form['evaluation'] = evaluation.pk
        response = form.submit('target_state', value="published")

        form = response.forms["evaluation-operation-form"]
        form['send_email_contributor'] = contributors
        form['send_email_participant'] = participants
        form.submit()

        evaluation = evaluation.course.semester.evaluations.first()
        evaluation.unpublish()
        evaluation.save()

    def test_publish_notifications(self):
        participant1 = baker.make(UserProfile, email="foo@example.com")
        participant2 = baker.make(UserProfile, email="bar@example.com")
        contributor1 = baker.make(UserProfile, email="contributor@example.com")

        evaluation = baker.make(Evaluation, course=self.course, state='reviewed',
                                participants=[participant1, participant2], voters=[participant1, participant2])
        baker.make(Contribution, contributor=contributor1, evaluation=evaluation)

        self.helper_publish_evaluation_with_publish_notifications_for(evaluation, contributors=False, participants=False)
        self.assertEqual(len(mail.outbox), 0)
        mail.outbox = []

        self.helper_publish_evaluation_with_publish_notifications_for(evaluation, contributors=True, participants=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [contributor1.email])
        mail.outbox = []

        self.helper_publish_evaluation_with_publish_notifications_for(evaluation, contributors=False, participants=True)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn([participant1.email], [mail.outbox[0].to, mail.outbox[1].to])
        self.assertIn([participant2.email], [mail.outbox[0].to, mail.outbox[1].to])
        mail.outbox = []

        self.helper_publish_evaluation_with_publish_notifications_for(evaluation, contributors=True, participants=True)
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn([participant1.email], [mail.outbox[0].to, mail.outbox[1].to, mail.outbox[2].to])
        self.assertIn([participant2.email], [mail.outbox[0].to, mail.outbox[1].to, mail.outbox[2].to])
        self.assertIn([contributor1.email], [mail.outbox[0].to, mail.outbox[1].to, mail.outbox[2].to])
        mail.outbox = []

    def helper_semester_state_views(self, evaluation, old_state, new_state):
        page = self.app.get("/staff/semester/1", user=self.manager)
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
        participant1 = baker.make(UserProfile, email="foo@example.com")
        participant2 = baker.make(UserProfile, email="bar@example.com")
        evaluation = baker.make(Evaluation, course=self.course, state='reviewed',
                                participants=[participant1, participant2], voters=[participant1, participant2])

        self.helper_semester_state_views(evaluation, "reviewed", "published")
        self.assertEqual(len(mail.outbox), 2)

    def test_semester_reset_1(self):
        evaluation = baker.make(Evaluation, course=self.course, state='prepared')
        self.helper_semester_state_views(evaluation, "prepared", "new")

    def test_semester_reset_2(self):
        evaluation = baker.make(Evaluation, course=self.course, state='approved')
        self.helper_semester_state_views(evaluation, "approved", "new")

    def test_semester_contributor_ready_1(self):
        evaluation = baker.make(Evaluation, course=self.course, state='new')
        self.helper_semester_state_views(evaluation, "new", "prepared")

    def test_semester_contributor_ready_2(self):
        evaluation = baker.make(Evaluation, course=self.course, state='editor_approved')
        self.helper_semester_state_views(evaluation, "editor_approved", "prepared")

    def test_semester_unpublish(self):
        evaluation = baker.make(Evaluation, course=self.course, state='published', _participant_count=0, _voter_count=0)
        self.helper_semester_state_views(evaluation, "published", "reviewed")

    def test_operation_start_evaluation(self):
        evaluation = baker.make(Evaluation, state='approved', course=self.course)
        urloptions = '?evaluation={}&target_state=in_evaluation'.format(evaluation.pk)

        response = self.app.get(self.url + urloptions, user=self.manager)
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "manager"'.format(self.url))

        form = response.forms['evaluation-operation-form']
        form.submit()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'in_evaluation')

    def test_operation_prepare(self):
        evaluation = baker.make(Evaluation, state='new', course=self.course)
        urloptions = '?evaluation={}&target_state=prepared'.format(evaluation.pk)

        response = self.app.get(self.url + urloptions, user=self.manager)
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "manager"'.format(self.url))
        form = response.forms['evaluation-operation-form']
        form.submit()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'prepared')

    def submit_operation_prepare_form(self, url_options):
        actual_emails = []

        def mock(email_template, user, subject_params, body_params, use_cc, additional_cc_users=None, request=None):
            actual_emails.append({
                'user': user,
                'subject': email_template.subject,
                'subject_params': subject_params,
                'body': email_template.body,
                'body_params': body_params,
                'use_cc': use_cc,
                'additional_cc_users': set(additional_cc_users),
            })

        response = self.app.get(self.url + url_options, user=self.manager)
        form = response.forms['evaluation-operation-form']
        form['send_email'] = True
        form['email_subject'] = 'New evaluations ready for review'
        form['email_body'] = 'There are evaluations that need your approval.'

        with patch.object(EmailTemplate, 'send_to_user', mock):
            form.submit()

        return actual_emails

    def test_operation_prepare_sends_email_to_responsible(self):
        evaluation = baker.make(Evaluation, state='new', course=self.course)
        url_options = '?evaluation={}&target_state=prepared'.format(evaluation.pk)
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(actual_emails, [{
            'user': self.responsible,
            'subject': 'New evaluations ready for review',
            'subject_params': {},
            'body': 'There are evaluations that need your approval.',
            'body_params': {'user': self.responsible, 'evaluations': [evaluation]},
            'use_cc': True,
            'additional_cc_users': set(),
        }])

    def test_operation_prepare_sends_one_email_to_each_responsible(self):
        other_responsible = baker.make(UserProfile, email='co-responsible@example.com')
        self.course.responsibles.add(other_responsible)
        evaluation = baker.make(Evaluation, state='new', course=self.course)
        url_options = '?evaluation={}&target_state=prepared'.format(evaluation.pk)
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 2)

        email_to_responsible = next(email for email in actual_emails if email['user'] == self.responsible)
        self.assertEqual(email_to_responsible['body_params'], {'user': self.responsible, 'evaluations': [evaluation]})

        email_to_other_responsible = next(email for email in actual_emails if email['user'] == other_responsible)
        self.assertEqual(email_to_other_responsible['body_params'], {'user': other_responsible, 'evaluations': [evaluation]})

    def test_operation_prepare_with_multiple_evaluations(self):
        responsible_b = baker.make(UserProfile, email='responsible-b@example.com')
        course_b = baker.make(Course, semester=self.semester, responsibles=[responsible_b])
        evaluation_a = baker.make(Evaluation, state='new', course=self.course)
        evaluation_b = baker.make(Evaluation, state='new', course=course_b)
        url_options = '?evaluation={}&evaluation={}&target_state=prepared'.format(evaluation_a.pk, evaluation_b.pk)
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 2)

        email_to_responsible = next(email for email in actual_emails if email['user'] == self.responsible)
        self.assertEqual(email_to_responsible['body_params'], {'user': self.responsible, 'evaluations': [evaluation_a]})

        email_to_responsible_b = next(email for email in actual_emails if email['user'] == responsible_b)
        self.assertEqual(email_to_responsible_b['body_params'], {'user': responsible_b, 'evaluations': [evaluation_b]})

    def test_operation_prepare_sends_email_with_editors_in_cc(self):
        editor_a = baker.make(UserProfile, email='editor-a@example.com')
        editor_b = baker.make(UserProfile, email='editor-b@example.com')
        evaluation = baker.make(Evaluation, state='new', course=self.course)
        baker.make(Contribution, evaluation=evaluation, contributor=editor_a, role=Contribution.Role.EDITOR)
        baker.make(Contribution, evaluation=evaluation, contributor=editor_b, role=Contribution.Role.EDITOR)
        url_options = '?evaluation={}&target_state=prepared'.format(evaluation.pk)
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 1)
        self.assertEqual(actual_emails[0]['additional_cc_users'], {editor_a, editor_b})

    def test_operation_prepare_does_not_put_responsible_into_cc(self):
        evaluation = baker.make(Evaluation, state='new', course=self.course)
        baker.make(Contribution, evaluation=evaluation, contributor=self.responsible, role=Contribution.Role.EDITOR)
        url_options = '?evaluation={}&target_state=prepared'.format(evaluation.pk)
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 1)
        self.assertEqual(actual_emails[0]['additional_cc_users'], set())

    def test_operation_prepare_does_not_send_email_to_contributors(self):
        contributor = baker.make(UserProfile, email='contributor@example.com')
        evaluation = baker.make(Evaluation, state='new', course=self.course)
        baker.make(Contribution, evaluation=evaluation, contributor=contributor, role=Contribution.Role.CONTRIBUTOR)
        url_options = '?evaluation={}&target_state=prepared'.format(evaluation.pk)
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 1)
        self.assertEqual(actual_emails[0]['additional_cc_users'], set())


class TestCourseCreateView(WebTest):
    url = '/staff/semester/1/course/create'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, pk=1)
        cls.course_type = baker.make(CourseType)
        cls.degree = baker.make(Degree)
        cls.responsible = baker.make(UserProfile)

    def test_course_create(self):
        """
            Tests the course creation view with one valid and one invalid input dataset.
        """
        response = self.app.get(self.url, user=self.manager, status=200)
        form = response.forms["course-form"]
        form["semester"] = self.semester.pk
        form["name_de"] = "dskr4jre35m6"
        form["name_en"] = ""  # empty name to get a validation error
        form["type"] = self.course_type.pk
        form["degrees"] = [self.degree.pk]
        form["is_private"] = False
        form["responsibles"] = [self.responsible.pk]

        response = form.submit("operation", value="save")
        self.assertIn("This field is required", response)
        self.assertFalse(Course.objects.exists())

        form["name_en"] = "asdf"  # now do it right

        form.submit("operation", value="save")
        self.assertEqual(Course.objects.get().name_de, "dskr4jre35m6")


class TestSingleResultCreateView(WebTest):
    url = '/staff/semester/1/singleresult/create'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.course = baker.make(Course, semester=baker.make(Semester, pk=1))

    def test_course_is_prefilled(self):
        response = self.app.get(f'{self.url}/{self.course.pk}', user=self.manager, status=200)
        form = response.context['form']
        self.assertEqual(form['course'].initial, self.course.pk)

    def test_single_result_create(self):
        """
            Tests the single result creation view with one valid and one invalid input dataset.
        """
        response = self.app.get(self.url, user=self.manager, status=200)
        form = response.forms["single-result-form"]
        form["course"] = self.course.pk
        form["name_de"] = "qwertz"
        form["name_en"] = "qwertz"
        form["answer_1"] = 6
        form["answer_3"] = 2
        # missing event_date to get a validation error

        form.submit()
        self.assertFalse(Evaluation.objects.exists())

        form["event_date"] = "2014-01-01"  # now do it right

        form.submit()
        self.assertEqual(Evaluation.objects.get().name_de, "qwertz")


class TestEvaluationCreateView(WebTest):
    url = '/staff/semester/1/evaluation/create'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.course = baker.make(Course, semester=baker.make(Semester, pk=1))
        cls.q1 = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        cls.q2 = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)

    def test_course_is_prefilled(self):
        response = self.app.get(f'{self.url}/{self.course.pk}', user=self.manager, status=200)
        form = response.context['evaluation_form']
        self.assertEqual(form['course'].initial, self.course.pk)

    def test_evaluation_create(self):
        """
            Tests the evaluation creation view with one valid and one invalid input dataset.
        """
        response = self.app.get(self.url, user=self.manager, status=200)
        form = response.forms["evaluation-form"]
        form["course"] = self.course.pk
        form["name_de"] = "lfo9e7bmxp1xi"
        form["name_en"] = "asdf"
        form["vote_start_datetime"] = "2099-01-01 00:00:00"
        form["vote_end_date"] = "2014-01-01"  # wrong order to get the validation error
        form["general_questionnaires"] = [self.q1.pk]
        form["wait_for_grade_upload_before_publishing"] = True

        form['contributions-TOTAL_FORMS'] = 1
        form['contributions-INITIAL_FORMS'] = 0
        form['contributions-MAX_NUM_FORMS'] = 5
        form['contributions-0-evaluation'] = ''
        form['contributions-0-contributor'] = self.manager.pk
        form['contributions-0-questionnaires'] = [self.q2.pk]
        form['contributions-0-order'] = 0
        form['contributions-0-role'] = Contribution.Role.EDITOR
        form['contributions-0-textanswer_visibility'] = Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS

        form.submit()
        self.assertFalse(Evaluation.objects.exists())

        form["vote_start_datetime"] = "2014-01-01 00:00:00"
        form["vote_end_date"] = "2099-01-01"  # now do it right

        form.submit()
        self.assertEqual(Evaluation.objects.get().name_de, "lfo9e7bmxp1xi")


class TestEvaluationCopyView(WebTest):
    url = '/staff/semester/1/evaluation/1/copy'

    @classmethod
    def setUpTestData(cls):
        cls.manager = baker.make(UserProfile, email='manager@institution.example.com', groups=[Group.objects.get(name='Manager')])
        cls.semester = baker.make(Semester, pk=1)
        cls.course = baker.make(Course, semester=cls.semester)
        cls.evaluation = baker.make(
            Evaluation,
            pk=1,
            course=cls.course,
            name_de="Das Original",
            name_en="The Original",
        )
        cls.general_questionnaires = baker.make(Questionnaire, _quantity=5)
        cls.evaluation.general_contribution.questionnaires.set(cls.general_questionnaires)
        for __ in range(3):
            baker.make(
                Contribution,
                evaluation=cls.evaluation,
                contributor=baker.make(UserProfile),
            )

    def test_copy_forms_are_used(self):
        response = self.app.get(self.url, user=self.manager, status=200)
        self.assertIsInstance(response.context['evaluation_form'], EvaluationCopyForm)
        self.assertIsInstance(response.context['formset'], ContributionCopyFormSet)
        self.assertTrue(issubclass(response.context['formset'].form, ContributionCopyForm))

    def test_evaluation_copy(self):
        response = self.app.get(self.url, user=self.manager, status=200)
        form = response.forms['evaluation-form']
        form['name_de'] = "Eine Kopie"
        form['name_en'] = "A Copy"
        form.submit()

        # As we checked previously that the respective copy forms were used,
        # we don’t have to check for individual attributes, as those are checked in the respective form tests
        self.assertEqual(Evaluation.objects.count(), 2)
        copied_evaluation = Evaluation.objects.exclude(pk=self.evaluation.pk).get()
        self.assertEqual(copied_evaluation.contributions.count(), 4)


class TestCourseEditView(WebTest):
    url = '/staff/semester/1/course/1/edit'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        semester = baker.make(Semester, pk=1)
        degree = baker.make(Degree)
        responsible = baker.make(UserProfile)
        cls.course = baker.make(
            Course,
            name_en="Some name",
            semester=semester,
            degrees=[degree],
            responsibles=[responsible],
            pk=1,
            last_modified_user=cls.manager,
            last_modified_time=datetime.datetime(2000, 1, 1, 0, 0),
        )

    def setUp(self):
        self.course = Course.objects.get(pk=self.course.pk)

    def test_edit_course(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["course-form"]
        form['name_en'] = "A different name"
        form.submit("operation", value="save")
        self.course = Course.objects.get(pk=self.course.pk)
        self.assertEqual(self.course.name_en, "A different name")

    def test_last_modified_user(self):
        """
            Tests whether saving only changes the last_modified_user if changes were made.
        """
        test_user = baker.make(UserProfile, email='test_user@institution.example.com', groups=[Group.objects.get(name='Manager')])

        old_name_en = self.course.name_en
        old_last_modified_user = self.course.last_modified_user
        old_last_modified_time = self.course.last_modified_time
        self.assertEqual(old_last_modified_user.email, self.manager.email)
        self.assertEqual(old_last_modified_time, datetime.datetime(2000, 1, 1, 0, 0))

        page = self.app.get(self.url, user=test_user.email, status=200)
        form = page.forms["course-form"]
        # save without changes
        form.submit(name="operation", value="save")

        # no changes should have been made
        self.course = Course.objects.get(pk=self.course.pk)
        self.assertEqual(self.course.last_modified_user, old_last_modified_user)
        self.assertEqual(self.course.last_modified_time, datetime.datetime(2000, 1, 1, 0, 0))
        self.assertEqual(self.course.name_en, old_name_en)

        page = self.app.get(self.url, user=test_user.email, status=200)
        form = page.forms["course-form"]
        form["name_en"] = "Test name"
        # approve after changes
        form.submit(name="operation", value="save")

        self.course = Course.objects.get(pk=self.course.pk)
        self.assertEqual(self.course.last_modified_user, test_user)
        self.assertTrue(datetime.datetime.now() - self.course.last_modified_time < datetime.timedelta(0, 1, 0))
        self.assertEqual(self.course.name_en, "Test name")


@override_settings(REWARD_POINTS=[
    (1 / 3, 1),
    (2 / 3, 2),
    (3 / 3, 3),
])
class TestEvaluationEditView(WebTest):
    url = '/staff/semester/1/evaluation/1/edit'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        semester = baker.make(Semester, pk=1)
        degree = baker.make(Degree)
        responsible = baker.make(UserProfile)
        cls.editor = baker.make(UserProfile)
        cls.evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, semester=semester, degrees=[degree], responsibles=[responsible]),
            pk=1,
            last_modified_user=cls.manager,
            vote_start_datetime=datetime.datetime(2099, 1, 1, 0, 0),
            vote_end_date=datetime.date(2099, 12, 31),
        )
        baker.make(Questionnaire, questions=[baker.make(Question)])
        cls.evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])
        baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=responsible,
            order=0,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=cls.editor,
            order=1,
            role=Contribution.Role.EDITOR,
        )

    def setUp(self):
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)

    def test_edit_evaluation(self):
        page = self.app.get(self.url, user=self.manager)

        # remove editor rights
        form = page.forms["evaluation-form"]
        form['contributions-1-role'] = Contribution.Role.CONTRIBUTOR
        form.submit("operation", value="save")
        self.assertEqual(self.evaluation.contributions.get(contributor=self.editor).role, Contribution.Role.CONTRIBUTOR)

    def test_participant_removal_reward_point_granting_message(self):
        already_evaluated = baker.make(Evaluation, pk=2, course=baker.make(Course, semester=self.evaluation.course.semester))
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        other = baker.make(UserProfile, evaluations_participating_in=[self.evaluation])
        student = baker.make(UserProfile, email="foo@institution.example.com",
            evaluations_participating_in=[self.evaluation, already_evaluated], evaluations_voted_for=[already_evaluated])

        page = self.app.get(self.url, user=self.manager)

        # remove a single participant
        form = page.forms['evaluation-form']
        form['participants'] = [other.pk]
        page = form.submit('operation', value='save').follow()

        self.assertIn("The removal as participant has granted the user &quot;{}&quot; 3 reward points for the semester.".format(student.email), page)

    def test_remove_participants(self):
        already_evaluated = baker.make(Evaluation, pk=2, course=baker.make(Course, semester=self.evaluation.course.semester))
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        student = baker.make(UserProfile, evaluations_participating_in=[self.evaluation])

        for name in ["a", "b", "c", "d", "e"]:
            baker.make(UserProfile, email="{}@institution.example.com".format(name),
                evaluations_participating_in=[self.evaluation, already_evaluated], evaluations_voted_for=[already_evaluated])

        page = self.app.get(self.url, user=self.manager)

        # remove five participants
        form = page.forms['evaluation-form']
        form['participants'] = [student.pk]
        page = form.submit('operation', value='save').follow()

        for name in ["a", "b", "c", "d", "e"]:
            self.assertIn("The removal as participant has granted the user &quot;{}@institution.example.com&quot; 3 reward points for the semester.".format(name), page)

    def test_remove_participants_proportional_reward_points(self):
        already_evaluated = baker.make(Evaluation, pk=2, course=baker.make(Course, semester=self.evaluation.course.semester))
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        student = baker.make(UserProfile, evaluations_participating_in=[self.evaluation])

        for name, points_granted in [("a", 0), ("b", 1), ("c", 2), ("d", 3)]:
            user = baker.make(UserProfile, email="{}@institution.example.com".format(name),
                evaluations_participating_in=[self.evaluation, already_evaluated], evaluations_voted_for=[already_evaluated])
            RewardPointGranting.objects.create(user_profile=user, semester=self.evaluation.course.semester, value=points_granted)

        page = self.app.get(self.url, user=self.manager)

        # remove four participants
        form = page.forms['evaluation-form']
        form['participants'] = [student.pk]
        page = form.submit('operation', value='save').follow()

        self.assertIn("The removal as participant has granted the user &quot;a@institution.example.com&quot; 3 reward points for the semester.", page)
        self.assertIn("The removal as participant has granted the user &quot;b@institution.example.com&quot; 2 reward points for the semester.", page)
        self.assertIn("The removal as participant has granted the user &quot;c@institution.example.com&quot; 1 reward point for the semester.", page)
        self.assertNotIn("The removal as participant has granted the user &quot;d@institution.example.com&quot;", page)

    def test_last_modified_user(self):
        """
            Tests whether the button "Save and approve" does only change the
            last_modified_user if changes were made.
        """
        test_user = baker.make(UserProfile, email='approve_test_user@institution.example.com', groups=[Group.objects.get(name='Manager')])

        old_name_de = self.evaluation.name_de
        old_vote_start_datetime = self.evaluation.vote_start_datetime
        old_vote_end_date = self.evaluation.vote_end_date
        old_last_modified_user = self.evaluation.last_modified_user
        old_state = self.evaluation.state
        self.assertEqual(old_last_modified_user.email, self.manager.email)
        self.assertEqual(old_state, "new")

        page = self.app.get(self.url, user=test_user, status=200)
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

        page = self.app.get(self.url, user=test_user, status=200)
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

        self.assertEqual(self.evaluation.last_modified_user, self.manager)
        last_modified_time_before = self.evaluation.last_modified_time

        test_user = baker.make(
            UserProfile,
            email='approve_test_user@institution.example.com',
            groups=[Group.objects.get(name='Manager')]
        )
        page = self.app.get(self.url, user=test_user, status=200)
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

        test_user = baker.make(
            UserProfile,
            email='approve_test_user@institution.example.com',
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

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]

        semester = baker.make(Semester, pk=1)
        responsible = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, course=baker.make(Course, semester=semester, responsibles=[responsible]), pk=1)
        contribution = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=responsible,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            questionnaires=[Questionnaire.single_result_questionnaire()],
        )

        question = Questionnaire.single_result_questionnaire().questions.get()
        baker.make(RatingAnswerCounter, question=question, contribution=contribution, answer=1, count=5)
        baker.make(RatingAnswerCounter, question=question, contribution=contribution, answer=2, count=15)
        baker.make(RatingAnswerCounter, question=question, contribution=contribution, answer=3, count=40)
        baker.make(RatingAnswerCounter, question=question, contribution=contribution, answer=4, count=60)
        baker.make(RatingAnswerCounter, question=question, contribution=contribution, answer=5, count=30)


class TestEvaluationPreviewView(WebTestWith200Check):
    url = '/staff/semester/1/evaluation/1/preview'

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]

        semester = baker.make(Semester, pk=1)
        evaluation = baker.make(Evaluation, course=baker.make(Course, semester=semester), pk=1)
        evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])


class TestEvaluationImportPersonsView(WebTest):
    url = "/staff/semester/1/evaluation/1/person_management"
    filename_valid = os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls")
    filename_invalid = os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls")
    filename_random = os.path.join(settings.BASE_DIR, "staff/fixtures/random.random")

    @classmethod
    def setUpTestData(cls):
        semester = baker.make(Semester, pk=1)
        cls.manager = make_manager()
        cls.evaluation = baker.make(Evaluation, pk=1, course=baker.make(Course, semester=semester))
        profiles = baker.make(UserProfile, _quantity=42)
        cls.evaluation2 = baker.make(Evaluation, pk=2, course=baker.make(Course, semester=semester), participants=profiles)

    @classmethod
    def tearDown(cls):
        # delete the uploaded file again so other tests can start with no file guaranteed
        helper_delete_all_import_files(cls.manager.id)

    def test_import_valid_participants_file(self):
        page = self.app.get(self.url, user=self.manager)

        original_participant_count = self.evaluation.participants.count()

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test-participants")

        self.assertContains(page, 'Import previously uploaded file')
        self.assertEqual(self.evaluation.participants.count(), original_participant_count)

        form = page.forms["participant-import-form"]
        form.submit(name="operation", value="import-participants")
        self.assertEqual(self.evaluation.participants.count(), original_participant_count + 2)

        page = self.app.get(self.url, user=self.manager)
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_copy_participants(self):
        page = self.app.get(self.url, user=self.manager)

        original_participant_count = self.evaluation.participants.count()

        form = page.forms["participant-copy-form"]
        form["evaluation"] = str(self.evaluation2.pk)
        page = form.submit(name="operation", value="copy-participants")

        self.assertEqual(self.evaluation.participants.count(), original_participant_count + self.evaluation2.participants.count())

    def test_import_valid_contributors_file(self):
        page = self.app.get(self.url, user=self.manager)

        original_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()

        form = page.forms["contributor-import-form"]
        form["excel_file"] = (self.filename_valid,)
        page = form.submit(name="operation", value="test-contributors")

        self.assertContains(page, 'Import previously uploaded file')
        self.assertEqual(UserProfile.objects.filter(contributions__evaluation=self.evaluation).count(), original_contributor_count)

        form = page.forms["contributor-import-form"]
        form.submit(name="operation", value="import-contributors")
        self.assertEqual(UserProfile.objects.filter(contributions__evaluation=self.evaluation).count(), original_contributor_count + 2)

        page = self.app.get(self.url, user=self.manager)
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_copy_contributors(self):
        page = self.app.get(self.url, user=self.manager)

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
        page = self.app.get(self.url, user=self.manager)

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
        baker.make(UserProfile, email="lucilia.manilium@institution.example.com")

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)

        reply = form.submit(name="operation", value="test-participants")
        self.assertContains(reply, "The existing user would be overwritten with the following data:<br />"
                " -  None None, lucilia.manilium@institution.example.com (existing)<br />"
                " -  Lucilia Manilium, lucilia.manilium@institution.example.com (new)")

    def test_import_contributors_error_handling(self):
        """
        Tests whether errors given from the importer are displayed
        """
        page = self.app.get(self.url, user=self.manager)

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
        baker.make(UserProfile, email="lucilia.manilium@institution.example.com")

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["contributor-import-form"]
        form["excel_file"] = (self.filename_valid,)

        reply = form.submit(name="operation", value="test-contributors")
        self.assertContains(reply, "The existing user would be overwritten with the following data:<br />"
                " -  None None, lucilia.manilium@institution.example.com (existing)<br />"
                " -  Lucilia Manilium, lucilia.manilium@institution.example.com (new)")

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        form["excel_file"] = (self.filename_valid,)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_invalid_contributor_upload_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["contributor-import-form"]
        page = form.submit(name="operation", value="test-contributors")

        self.assertContains(page, 'This field is required.')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_invalid_participant_upload_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        page = form.submit(name="operation", value="test-participants")

        self.assertContains(page, 'This field is required.')
        self.assertNotContains(page, 'Import previously uploaded file')

    def test_invalid_contributor_import_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["contributor-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        reply = form.submit(name="operation", value="import-contributors", expect_errors=True)

        self.assertEqual(reply.status_code, 400)

    def test_invalid_participant_import_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        reply = form.submit(name="operation", value="import-participants", expect_errors=True)

        self.assertEqual(reply.status_code, 400)


class TestEvaluationEmailView(WebTest):
    url = '/staff/semester/1/evaluation/1/email'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        semester = baker.make(Semester, pk=1)
        participant1 = baker.make(UserProfile, email="foo@example.com")
        participant2 = baker.make(UserProfile, email="bar@example.com")
        baker.make(Evaluation, pk=1, course=baker.make(Course, semester=semester), participants=[participant1, participant2])

    def test_emails_are_sent(self):
        page = self.app.get(self.url, user=self.manager, status=200)
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
        cls.manager = make_manager()
        semester = baker.make(Semester, pk=1)
        student1 = baker.make(UserProfile, email="student@institution.example.com")
        cls.student2 = baker.make(UserProfile, email="student2@example.com")

        cls.evaluation = baker.make(
            Evaluation,
            pk=1,
            course=baker.make(Course, semester=semester),
            participants=[student1, cls.student2],
            voters=[student1],
            state="in_evaluation"
        )
        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=top_general_questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])

        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, questionnaire=questionnaire, type=Question.TEXT)
        contribution = baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=baker.make(UserProfile),
            questionnaires=[questionnaire],
        )
        cls.answer = 'should show up'
        baker.make(TextAnswer, contribution=contribution, question=question, answer=cls.answer)

    def test_textanswers_showing_up(self):
        # in an evaluation with only one voter the view should not be available
        self.app.get(self.url, user=self.manager, status=403)

        # add additional voter
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)

        # now it should work
        self.app.get(self.url, user=self.manager, status=200)

    def test_textanswers_quick_view(self):
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)
        page = self.app.get(self.url, user=self.manager, status=200)
        self.assertContains(page, self.answer)

    def test_textanswers_full_view(self):
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)
        page = self.app.get(self.url + '?view=full', user=self.manager, status=200)
        self.assertContains(page, self.answer)


class TestEvaluationTextAnswerEditView(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        student1 = baker.make(UserProfile, email="student1@institution.example.com")
        cls.student2 = baker.make(UserProfile, email="student2@example.com")

        semester = baker.make(Semester, pk=1)
        cls.evaluation = baker.make(
            Evaluation,
            pk=1,
            course=baker.make(Course, semester=semester),
            participants=[student1, cls.student2],
            voters=[student1],
            state="in_evaluation"
        )
        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=top_general_questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])
        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, questionnaire=questionnaire, type=Question.TEXT)

        contribution = baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=baker.make(UserProfile),
            questionnaires=[questionnaire],
        )
        cls.text_answer = baker.make(
            TextAnswer,
            contribution=contribution,
            question=question,
            answer='test answer text',
        )

        cls.url = f'/staff/semester/1/evaluation/1/textanswer/{cls.text_answer.id}/edit'

    def test_textanswers_showing_up(self):
        # in an evaluation with only one voter the view should not be available
        self.app.get(self.url, user=self.manager, status=403)

        # add additional voter
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)

        # now it should work
        response = self.app.get(self.url, user=self.manager)

        form = response.forms['textanswer-edit-form']
        self.assertEqual(form['answer'].value, 'test answer text')
        form['answer'] = 'edited answer text'
        form.submit()

        self.text_answer.refresh_from_db()
        self.assertEqual(self.text_answer.answer, 'edited answer text')


class TestQuestionnaireNewVersionView(WebTest):
    url = '/staff/questionnaire/2/new_version'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.name_de_orig = 'kurzer name'
        cls.name_en_orig = 'short name'
        questionnaire = baker.make(Questionnaire, id=2, name_de=cls.name_de_orig, name_en=cls.name_en_orig)
        baker.make(Question, questionnaire=questionnaire)

    def test_changes_old_title(self):
        page = self.app.get(url=self.url, user=self.manager)
        form = page.forms['questionnaire-form']

        form.submit()

        timestamp = datetime.date.today()
        new_name_de = '{} (until {})'.format(self.name_de_orig, str(timestamp))
        new_name_en = '{} (until {})'.format(self.name_en_orig, str(timestamp))

        self.assertTrue(Questionnaire.objects.filter(name_de=self.name_de_orig, name_en=self.name_en_orig).exists())
        self.assertTrue(Questionnaire.objects.filter(name_de=new_name_de, name_en=new_name_en).exists())

    def test_no_second_update(self):
        # First save.
        page = self.app.get(url=self.url, user=self.manager)
        form = page.forms['questionnaire-form']
        form.submit()

        # Second try.
        new_questionnaire = Questionnaire.objects.get(name_de=self.name_de_orig)
        page = self.app.get(url=f'/staff/questionnaire/{new_questionnaire.id}/new_version', user=self.manager)

        # We should get redirected back to the questionnaire index.
        self.assertEqual(page.status_code, 302)
        self.assertEqual(page.location, '/staff/questionnaire/')


class TestQuestionnaireCreateView(WebTest):
    url = "/staff/questionnaire/create"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_create_questionnaire(self):
        page = self.app.get(self.url, user=self.manager)

        questionnaire_form = page.forms["questionnaire-form"]
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire"
        questionnaire_form['questions-0-text_de'] = "Frage 1"
        questionnaire_form['questions-0-text_en'] = "Question 1"
        questionnaire_form['questions-0-type'] = Question.TEXT
        questionnaire_form['order'] = 0
        questionnaire_form['type'] = Questionnaire.Type.TOP
        questionnaire_form.submit().follow()

        # retrieve new questionnaire
        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
        self.assertEqual(questionnaire.questions.count(), 1)

    def test_create_empty_questionnaire(self):
        page = self.app.get(self.url, user=self.manager)

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
        cls.manager = make_manager()
        cls.contributor_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        cls.top_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        cls.bottom_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.BOTTOM)

    def test_ordering(self):
        content = self.app.get(self.url, user=self.manager).body.decode()
        top_index = content.index(self.top_questionnaire.name)
        contributor_index = content.index(self.contributor_questionnaire.name)
        bottom_index = content.index(self.bottom_questionnaire.name)

        self.assertTrue(top_index < contributor_index < bottom_index)


class TestQuestionnaireEditView(WebTestWith200Check):
    url = '/staff/questionnaire/2/edit'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.test_users = [cls.manager]

        evaluation = baker.make(Evaluation, state='in_evaluation')
        cls.questionnaire = baker.make(Questionnaire, id=2)
        baker.make(Contribution, questionnaires=[cls.questionnaire], evaluation=evaluation)

        baker.make(Question, questionnaire=cls.questionnaire)

    def test_allowed_type_changes_on_used_questionnaire(self):
        # top to bottom
        self.questionnaire.type = Questionnaire.Type.TOP
        self.questionnaire.save()

        page = self.app.get(self.url, user=self.manager)
        form = page.forms['questionnaire-form']
        self.assertEqual(form['type'].options, [('10', True, 'Top questionnaire'), ('30', False, 'Bottom questionnaire')])

        # bottom to top
        self.questionnaire.type = Questionnaire.Type.BOTTOM
        self.questionnaire.save()

        page = self.app.get(self.url, user=self.manager)
        form = page.forms['questionnaire-form']
        self.assertEqual(form['type'].options, [('10', False, 'Top questionnaire'), ('30', True, 'Bottom questionnaire')])

        # contributor has no other possible type
        self.questionnaire.type = Questionnaire.Type.CONTRIBUTOR
        self.questionnaire.save()

        page = self.app.get(self.url, user=self.manager)
        form = page.forms['questionnaire-form']
        self.assertEqual(form['type'].options, [('20', True, 'Contributor questionnaire')])


class TestQuestionnaireViewView(WebTestWith200Check):
    url = '/staff/questionnaire/2'

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]

        questionnaire = baker.make(Questionnaire, id=2)
        baker.make(Question, questionnaire=questionnaire, type=Question.TEXT)
        baker.make(Question, questionnaire=questionnaire, type=Question.GRADE)
        baker.make(Question, questionnaire=questionnaire, type=Question.LIKERT)


class TestQuestionnaireCopyView(WebTest):
    url = '/staff/questionnaire/2/copy'

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        questionnaire = baker.make(Questionnaire, id=2)
        baker.make(Question, questionnaire=questionnaire)

    def test_not_changing_name_fails(self):
        response = self.app.get(self.url, user=self.manager, status=200)
        response = response.forms[1].submit("", status=200)
        self.assertIn("already exists", response)

    def test_copy_questionnaire(self):
        page = self.app.get(self.url, user=self.manager)

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
        cls.manager = make_manager()
        cls.q1 = baker.make(Questionnaire)
        cls.q2 = baker.make(Questionnaire)
        baker.make(Contribution, questionnaires=[cls.q1])

    def test_questionnaire_deletion(self):
        """
            Tries to delete two questionnaires via the respective post request,
            only the second attempt should succeed.
        """
        self.assertFalse(Questionnaire.objects.get(pk=self.q1.pk).can_be_deleted_by_manager)
        response = self.app.post(
            "/staff/questionnaire/delete",
            params={"questionnaire_id": self.q1.pk},
            user=self.manager,
            expect_errors=True,
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Questionnaire.objects.filter(pk=self.q1.pk).exists())

        self.assertTrue(Questionnaire.objects.get(pk=self.q2.pk).can_be_deleted_by_manager)
        response = self.app.post(
            "/staff/questionnaire/delete",
            params={"questionnaire_id": self.q2.pk},
            user=self.manager,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Questionnaire.objects.filter(pk=self.q2.pk).exists())


class TestCourseTypeView(WebTest):
    url = "/staff/course_types/"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    @staticmethod
    def set_import_names(field, value):
        # Webtest will check that all values are included in the options, so we modify the options beforehand
        field.options = [(name, False, name) for name in value]
        field.value = value

    def test_page_displays_something(self):
        CourseType.objects.create(name_de='uZJcsl0rNc', name_en='uZJcsl0rNc')
        page = self.app.get(self.url, user=self.manager, status=200)
        self.assertIn('uZJcsl0rNc', page)

    def test_course_type_form(self):
        """
            Adds a course type via the staff form and verifies that the type was created in the db.
        """
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms['course-type-form']
        form['form-0-name_de'].value = "Vorlesung"
        form['form-0-name_en'].value = "Lecture"
        self.set_import_names(form['form-0-import_names'], ["Vorlesung", "V"])
        response = form.submit().follow()
        self.assertContains(response, "Successfully")

        self.assertEqual(CourseType.objects.count(), 1)
        self.assertTrue(CourseType.objects.filter(name_de="Vorlesung", name_en="Lecture", import_names=["Vorlesung", "V"]).exists())

    def test_import_names_duplicated_error(self):
        baker.make(CourseType, _quantity=2)
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms['course-type-form']
        self.set_import_names(form['form-0-import_names'], ["Vorlesung", "v"])
        self.set_import_names(form['form-1-import_names'], ["Veranstaltung", "V"])
        response = form.submit()
        self.assertContains(response, 'Import name &quot;V&quot; is duplicated. Import names are not case sensitive.')


class TestCourseTypeMergeSelectionView(WebTest):
    url = "/staff/course_types/merge"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.main_type = baker.make(CourseType, name_en="A course type")
        cls.other_type = baker.make(CourseType, name_en="Obsolete course type")

    def test_same_evaluation_fails(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["course-type-merge-selection-form"]
        form["main_type"] = self.main_type.pk
        form["other_type"] = self.main_type.pk
        response = form.submit()
        self.assertIn("You must select two different course types", str(response))


class TestCourseTypeMergeView(WebTest):
    url = "/staff/course_types/1/merge/2"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.main_type = baker.make(CourseType, pk=1, name_en="A course type", import_names=['M'])
        cls.other_type = baker.make(CourseType, pk=2, name_en="Obsolete course type", import_names=['O'])
        baker.make(Course, type=cls.main_type)
        baker.make(Course, type=cls.other_type)

    def test_merge_works(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["course-type-merge-form"]
        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertFalse(CourseType.objects.filter(name_en="Obsolete course type").exists())
        self.main_type.refresh_from_db()
        self.assertEqual(self.main_type.import_names, ['M', 'O'])
        self.assertEqual(Course.objects.filter(type=self.main_type).count(), 2)
        for course in Course.objects.all():
            self.assertTrue(course.type == self.main_type)


class TestEvaluationTextAnswersUpdatePublishView(WebTest):
    url = reverse("staff:evaluation_textanswers_update_publish")
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.student1 = baker.make(UserProfile, email="student1@institution.example.com")
        cls.student2 = baker.make(UserProfile, email="student2@example.com")

        cls.evaluation = baker.make(
            Evaluation,
            participants=[cls.student1, cls.student2],
            voters=[cls.student1],
            state="in_evaluation",
        )
        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=top_general_questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])

    def helper(self, old_state, expected_new_state, action, expect_errors=False):
        textanswer = baker.make(TextAnswer, state=old_state)
        response = self.app.post(
            self.url,
            params={"id": textanswer.id, "action": action, "evaluation_id": self.evaluation.pk},
            user=self.manager,
            expect_errors=expect_errors,
        )
        if expect_errors:
            self.assertEqual(response.status_code, 403)
        else:
            self.assertEqual(response.status_code, 200)
            textanswer.refresh_from_db()
            self.assertEqual(textanswer.state, expected_new_state)

    def test_review_actions(self):
        # in an evaluation with only one voter reviewing should fail
        self.helper(TextAnswer.State.NOT_REVIEWED, TextAnswer.State.PUBLISHED, "publish", expect_errors=True)

        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)

        # now reviewing should work
        self.helper(TextAnswer.State.NOT_REVIEWED, TextAnswer.State.PUBLISHED, "publish")
        self.helper(TextAnswer.State.NOT_REVIEWED, TextAnswer.State.HIDDEN, "hide")
        self.helper(TextAnswer.State.NOT_REVIEWED, TextAnswer.State.PRIVATE, "make_private")
        self.helper(TextAnswer.State.PUBLISHED, TextAnswer.State.NOT_REVIEWED, "unreview")


class ParticipationArchivingTests(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_raise_403(self):
        """
            Tests whether inaccessible views on semesters/evaluations with
            archived participations correctly raise a 403.
        """
        semester = baker.make(Semester, participations_are_archived=True)

        semester_url = "/staff/semester/{}/".format(semester.pk)

        self.app.get(semester_url + "import", user=self.manager, status=403)
        self.app.get(semester_url + "assign", user=self.manager, status=403)
        self.app.get(semester_url + "evaluation/create", user=self.manager, status=403)
        self.app.get(semester_url + "evaluationoperation", user=self.manager, status=403)


class TestTemplateEditView(WebTest):
    url = "/staff/template/1"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_emailtemplate(self):
        """
            Tests the emailtemplate view with one valid and one invalid input datasets.
        """
        page = self.app.get(self.url, user=self.manager, status=200)
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
        cls.manager = make_manager()

    @staticmethod
    def set_import_names(field, value):
        # Webtest will check that all values are included in the options, so we modify the options beforehand
        field.options = [(name, False, name) for name in value]
        field.value = value

    def test_degree_form(self):
        """
            Adds a degree via the staff form and verifies that the degree was created in the db.
        """
        degree_count_before = Degree.objects.count()
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["degree-form"]
        last_form_id = int(form["form-TOTAL_FORMS"].value) - 1
        form[f'form-{last_form_id}-name_de'].value = "Diplom"
        form[f'form-{last_form_id}-name_en'].value = "Diploma"
        self.set_import_names(form[f'form-{last_form_id}-import_names'], ["Diplom", "D"])
        response = form.submit().follow()
        self.assertContains(response, "Successfully")

        self.assertEqual(Degree.objects.count(), degree_count_before + 1)
        self.assertTrue(Degree.objects.filter(name_de="Diplom", name_en="Diploma", import_names=["Diplom", "D"]).exists())

    def test_import_names_duplicated_error(self):
        baker.make(Degree, _quantity=2)
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms['degree-form']
        self.set_import_names(form['form-0-import_names'], ["Master of Arts", "M"])
        self.set_import_names(form['form-1-import_names'], ["Master of Science", "M"])
        response = form.submit()
        self.assertContains(response, 'Import name &quot;M&quot; is duplicated.')


class TestSemesterQuestionnaireAssignment(WebTest):
    url = "/staff/semester/1/assign"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, id=1)
        cls.course_type_1 = baker.make(CourseType)
        cls.course_type_2 = baker.make(CourseType)
        cls.responsible = baker.make(UserProfile)
        cls.questionnaire_1 = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        cls.questionnaire_2 = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        cls.questionnaire_responsible = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        cls.evaluation_1 = baker.make(
            Evaluation,
            course=baker.make(Course, semester=cls.semester, type=cls.course_type_1, responsibles=[cls.responsible]),
        )
        cls.evaluation_2 = baker.make(
            Evaluation,
            course=baker.make(Course, semester=cls.semester, type=cls.course_type_2, responsibles=[cls.responsible]),
        )
        baker.make(
            Contribution,
            contributor=cls.responsible,
            evaluation=cls.evaluation_1,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        baker.make(
            Contribution,
            contributor=cls.responsible,
            evaluation=cls.evaluation_2,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )

    def test_questionnaire_assignment(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["questionnaire-assign-form"]
        form[self.course_type_1.name] = [self.questionnaire_1.pk, self.questionnaire_2.pk]
        form[self.course_type_2.name] = [self.questionnaire_2.pk]
        form["All contributors"] = [self.questionnaire_responsible.pk]

        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertEqual(set(self.evaluation_1.general_contribution.questionnaires.all()), set([self.questionnaire_1, self.questionnaire_2]))
        self.assertEqual(set(self.evaluation_2.general_contribution.questionnaires.all()), set([self.questionnaire_2]))
        self.assertEqual(set(self.evaluation_1.contributions.get(contributor=self.responsible).questionnaires.all()), set([self.questionnaire_responsible]))
        self.assertEqual(set(self.evaluation_2.contributions.get(contributor=self.responsible).questionnaires.all()), set([self.questionnaire_responsible]))


class TestSemesterActiveStateBehaviour(WebTest):
    url = "/staff/semester/make_active"
    csrf_checks = False

    def test_make_other_semester_active(self):
        manager = make_manager()

        semester1 = baker.make(Semester, is_active=True)
        semester2 = baker.make(Semester)

        self.assertFalse(semester2.is_active)

        self.app.post(self.url, user=manager, status=200, params={
            "semester_id": semester2.id,
        })

        semester1.refresh_from_db()
        semester2.refresh_from_db()

        self.assertFalse(semester1.is_active)
        self.assertTrue(semester2.is_active)
