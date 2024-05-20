import csv
import datetime
import os
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Literal
from unittest.mock import PropertyMock, patch

import openpyxl
import xlrd
from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.db.models import Model
from django.http import HttpResponse
from django.test import override_settings
from django.test.testcases import TestCase
from django.urls import reverse
from django_webtest import WebTest
from model_bakery import baker

import evap.staff.fixtures.excel_files_test_data as excel_data
from evap.evaluation.models import (
    Contribution,
    Course,
    CourseType,
    Degree,
    EmailTemplate,
    Evaluation,
    FaqQuestion,
    Infotext,
    Question,
    Questionnaire,
    QuestionType,
    RatingAnswerCounter,
    Semester,
    TextAnswer,
    UserProfile,
    VoteTimestamp,
)
from evap.evaluation.tests.tools import (
    FuzzyInt,
    assert_no_database_modifications,
    create_evaluation_with_responsible_and_editor,
    let_user_vote_for_evaluation,
    make_manager,
    make_rating_answer_counters,
    render_pages,
    submit_with_modal,
)
from evap.grades.models import GradeDocument
from evap.results.tools import TextResult, cache_results, get_results
from evap.rewards.models import RewardPointGranting, SemesterActivation
from evap.staff.forms import ContributionCopyForm, ContributionCopyFormset, CourseCopyForm, EvaluationCopyForm
from evap.staff.tests.utils import (
    WebTestStaffMode,
    WebTestStaffModeWith200Check,
    helper_delete_all_import_files,
    helper_fill_infotext_formset,
    helper_set_dynamic_choices_field_value,
    run_in_staff_mode,
)
from evap.staff.tools import user_edit_link
from evap.staff.views import get_evaluations_with_prefetched_data
from evap.student.models import TextAnswerWarning


class DeleteViewTestMixin(ABC):
    csrf_checks = False

    # To be set by derived classes
    model_cls: type[Model]
    url: str
    permission_method_to_patch: tuple[type, str]

    @classmethod
    @abstractmethod
    def get_post_params(cls):
        pass

    @classmethod
    def setUpTestData(cls):
        cls.instance = baker.make(cls.model_cls)
        cls.user = make_manager()
        cls.post_params = cls.get_post_params()

    def test_valid_deletion(self):
        with patch.object(*self.permission_method_to_patch, True):
            self.app.post(self.url, user=self.user, params=self.post_params)
        self.assertFalse(self.model_cls.objects.filter(pk=self.instance.pk).exists())

    def test_invalid_deletion(self):
        with patch.object(*self.permission_method_to_patch, False):
            self.app.post(self.url, user=self.user, params=self.post_params, status=400)
        self.assertTrue(self.model_cls.objects.filter(pk=self.instance.pk).exists())


class TestDownloadSampleFileView(WebTestStaffMode):
    url = "/staff/download_sample_file/sample.xlsx"
    email_placeholder = "institution.com"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_sample_file_correctness(self):
        page = self.app.get(self.url, user=self.manager)

        found_institution_domains = 0
        book = openpyxl.load_workbook(BytesIO(page.body))
        for sheet in book:
            for row in sheet.values:
                for cell in row:
                    if cell is None:
                        continue

                    self.assertNotIn(self.email_placeholder, cell)

                    if "@" + settings.INSTITUTION_EMAIL_DOMAINS[0] in cell:
                        found_institution_domains += 1

        self.assertEqual(found_institution_domains, 2)


class TestStaffIndexView(WebTestStaffModeWith200Check):
    url = "/staff/"

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]


class TestStaffFAQView(WebTestStaffModeWith200Check):
    url = "/staff/faq/"

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]


class TestStaffFAQEditView(WebTestStaffModeWith200Check):
    @classmethod
    def setUpTestData(cls):
        faq_question = baker.make(FaqQuestion)

        cls.test_users = [make_manager()]
        cls.url = f"/staff/faq/{faq_question.section.pk}"


class TestStaffInfotextEditView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.url = "/staff/infotexts/"

    def test_infotext_edit_success(self):
        page = self.app.get(self.url, user=self.manager)
        formset = page.forms["infotext-formset"]

        helper_fill_infotext_formset(formset, 0, title_de="abc", title_en="def", content_de="ghi", content_en="jkl")
        helper_fill_infotext_formset(formset, 1)

        filled_form_id = formset["form-0-id"]
        empty_form_id = formset["form-1-id"]
        formset.submit()

        # check, that content arrived at database
        infotext = Infotext.objects.get(id=filled_form_id.value)
        self.assertEqual(infotext.title_de, "abc")
        self.assertEqual(infotext.title_en, "def")
        self.assertEqual(infotext.content_de, "ghi")
        self.assertEqual(infotext.content_en, "jkl")

        infotext = Infotext.objects.get(id=empty_form_id.value)
        self.assertTrue(infotext.is_empty())

    def test_infotext_edit_fail(self):
        page = self.app.get(self.url, user=self.manager)
        formset = page.forms["infotext-formset"]

        # submit invalid data
        helper_fill_infotext_formset(formset, 0, title_de="abc", title_en="def", content_de="ghi", content_en="jkl")
        helper_fill_infotext_formset(formset, 1, title_de="invalid infotext", content_en="no translations")

        empty_form_id = formset["form-0-id"]
        filled_form_id = formset["form-1-id"]
        formset.submit()

        # assert no infotexts changed
        infotext = Infotext.objects.get(id=empty_form_id.value)
        self.assertTrue(infotext.is_empty())

        infotext = Infotext.objects.get(id=filled_form_id.value)
        self.assertTrue(infotext.is_empty())


class TestUserIndexView(WebTestStaffMode):
    url = "/staff/user/"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.some_user = baker.make(UserProfile)

    def test_redirect(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["user-edit-form"]
        form["user"] = self.some_user.pk
        response = form.submit(status=302)
        self.assertEqual(response.location, f"/staff/user/{self.some_user.pk}/edit")


class TestUserListView(WebTestStaffMode):
    url = "/staff/user/list"

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
            state=Evaluation.State.PUBLISHED,
            course__semester=semester,
            _participant_count=1,
            _voter_count=1,
        )
        users = baker.make(UserProfile, _bulk_create=True, _quantity=num_users)
        participations = [Evaluation.participants.through(evaluation=evaluation, userprofile=user) for user in users]
        Evaluation.participants.through.objects.bulk_create(participations)

        with self.assertNumQueries(FuzzyInt(0, num_users - 1)):
            self.app.get(self.url, user=self.manager)


class TestUserCreateView(WebTestStaffMode):
    url = "/staff/user/create"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_user_is_created(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["user-form"]
        form["first_name_given"] = "asd"
        form["last_name"] = "asd"
        form["email"] = "a@b.de"

        form.submit()

        self.assertEqual(UserProfile.objects.order_by("pk").last().email, "a@b.de")


@override_settings(
    REWARD_POINTS=[
        (1 / 3, 1),
        (2 / 3, 2),
        (3 / 3, 3),
    ]
)
class TestUserEditView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.testuser = baker.make(UserProfile)
        cls.url = f"/staff/user/{cls.testuser.pk}/edit"

    def test_user_edit(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["user-form"]
        form["email"] = "test@institution.example.com"
        form.submit()
        self.assertTrue(UserProfile.objects.filter(email="test@institution.example.com").exists())

    def test_user_edit_duplicate_email(self):
        second_user = baker.make(UserProfile, email="test@institution.example.com")
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["user-form"]
        form["email"] = second_user.email
        page = form.submit()
        self.assertContains(
            page, "A user with this email address already exists. You probably want to merge the users."
        )

    @patch("evap.staff.forms.remove_user_from_represented_and_ccing_users")
    def test_inactive_edit(self, mock_remove):
        mock_remove.return_value = ["This text is supposed to be visible on the website."]
        baker.make(UserProfile, delegates=[self.testuser])
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["user-form"]
        form["is_inactive"] = True
        response = form.submit().follow()
        mock_remove.assert_called_once()
        mock_remove.assert_called_with(self.testuser)
        self.assertIn(mock_remove.return_value[0], response)

    def test_reward_points_granting_message(self):
        evaluation = baker.make(Evaluation, course__semester__is_active=True)
        already_evaluated = baker.make(Evaluation, course=baker.make(Course, semester=evaluation.course.semester))
        SemesterActivation.objects.create(semester=evaluation.course.semester, is_active=True)
        student = baker.make(
            UserProfile,
            email="foo@institution.example.com",
            evaluations_participating_in=[evaluation, already_evaluated],
            evaluations_voted_for=[already_evaluated],
        )

        page = self.app.get(reverse("staff:user_edit", args=[student.pk]), user=self.manager, status=200)
        form = page.forms["user-form"]
        form["evaluations_participating_in"] = [already_evaluated.pk]

        page = form.submit().follow()
        # fetch the user name, which became lowercased
        student.refresh_from_db()

        self.assertIn("Successfully updated user.", page)
        self.assertIn(
            f"The removal of evaluations has granted the user &quot;{student.email}&quot; "
            "3 reward points for the active semester.",
            page,
        )


class TestUserDeleteView(DeleteViewTestMixin, WebTestStaffMode):
    url = reverse("staff:user_delete")
    model_cls = UserProfile
    permission_method_to_patch = (UserProfile, "can_be_deleted_by_manager")

    @classmethod
    def get_post_params(cls):
        return {"user_id": cls.instance.pk}


class TestUserMergeSelectionView(WebTestStaffMode):
    url = reverse("staff:user_merge_selection")

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

        cls.main_user = baker.make(UserProfile, _fill_optional=["email"])
        cls.other_user = baker.make(UserProfile, _fill_optional=["email"])

    def test_redirection_user_merge_view(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-selection-form"]
        form["main_user"] = self.main_user.pk
        form["other_user"] = self.other_user.pk

        page = form.submit().follow()

        self.assertContains(page, self.main_user.email)
        self.assertContains(page, self.other_user.email)

    @override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.example.com", "student.institution.example.com"])
    def test_suggested_merge(self):
        suggested_merge_candidate = baker.make(UserProfile, email="user@student.institution.example.com")
        suggested_main_user = baker.make(UserProfile, email="user@institution.example.com")

        self.assertLess(suggested_merge_candidate.pk, suggested_main_user.pk)

        page = self.app.get(self.url, user=self.manager)

        expected_url = reverse("staff:user_merge", args=[suggested_main_user.pk, suggested_merge_candidate.pk])
        unexpected_url = reverse("staff:user_merge", args=[suggested_merge_candidate.pk, suggested_main_user.pk])

        self.assertContains(page, f'<a href="{expected_url}"')
        self.assertNotContains(page, f'<a href="{unexpected_url}"')


class TestUserMergeView(WebTestStaffModeWith200Check):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.test_users = [cls.manager]

        cls.main_user = baker.make(UserProfile)
        cls.other_user = baker.make(UserProfile)
        cls.url = f"/staff/user/{cls.main_user.pk}/merge/{cls.other_user.pk}"

    def test_shows_evaluations_participating_in(self):
        evaluation = baker.make(Evaluation, name_en="The journey of unit-testing", participants=[self.main_user])

        page = self.app.get(self.url, user=self.manager)
        self.assertContains(
            page,
            evaluation.name_en,
            count=2,
            msg_prefix="The evaluation name should be displayed twice: "
            "in the column of the participant and in the column of the merged data",
        )

    def test_shows_evaluations_voted_for(self):
        evaluation = baker.make(Evaluation, name_en="Voting theory", voters=[self.main_user])

        page = self.app.get(self.url, user=self.manager)
        self.assertContains(
            page,
            evaluation.name_en,
            count=2,
            msg_prefix="The evaluation name should be displayed twice: "
            "in the column of the voter and in the column of the merged data",
        )

    def test_shows_swap_users_option(self):
        page = self.app.get(self.url, user=self.manager)
        self.assertContains(page, f"/staff/user/{self.other_user.pk}/merge/{self.main_user.pk}")


class TestUserBulkUpdateView(WebTestStaffMode):
    url = "/staff/user/bulk_update"
    filename = os.path.join(settings.BASE_DIR, "staff/fixtures/test_user_bulk_update_file.txt")

    @classmethod
    def setUpTestData(cls):
        cls.random_excel_file_content = excel_data.random_file_content
        cls.manager = make_manager()

    def test_testrun_deletes_no_users(self):
        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-bulk-update-form"]

        form["user_file"] = (self.filename,)

        baker.make(UserProfile, is_active=False)
        users_before = set(UserProfile.objects.all())

        form.submit(name="operation", value="test", status=200)
        # No user got deleted.
        self.assertEqual(users_before, set(UserProfile.objects.all()))

        helper_delete_all_import_files(self.manager.id)

    @override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.example.com", "internal.example.com"])
    def test_multiple_email_matches_trigger_error(self):
        baker.make(UserProfile, email="testremove@institution.example.com")
        baker.make(
            UserProfile, first_name_given="Elisabeth", last_name="Fröhlich", email="testuser1@institution.example.com"
        )

        error_string = (
            "Multiple users match the email testuser1@institution.example.com:"
            "<br />Elisabeth Fröhlich (testuser1@institution.example.com)"
            "<br />Tony Kuchenbuch (testuser1@internal.example.com)"
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

        new_user = baker.make(
            UserProfile, first_name_given="Tony", last_name="Kuchenbuch", email="testuser1@internal.example.com"
        )
        expected_users.add(new_user)

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-bulk-update-form"]
        form["user_file"] = (self.filename,)
        response = form.submit(name="operation", value="test")

        self.assertNotIn(button_substring, response)
        self.assertIn(error_string, response)
        self.assertEqual(set(UserProfile.objects.all()), expected_users)

    @override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.example.com", "internal.example.com"])
    @patch("evap.staff.tools.remove_user_from_represented_and_ccing_users")
    def test_handles_users(self, mock_remove):
        mock_remove.return_value = ["This text is supposed to be visible on the website."]
        testuser1 = baker.make(UserProfile, email="testuser1@institution.example.com")
        testuser2 = baker.make(UserProfile, email="testuser2@institution.example.com")
        testuser1.delegates.set([testuser2])
        baker.make(UserProfile, email="testupdate@institution.example.com")
        contribution1 = baker.make(Contribution)
        semester = baker.make(Semester, participations_are_archived=True)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, semester=semester),
            _participant_count=0,
            _voter_count=0,
        )
        contribution2 = baker.make(Contribution, evaluation=evaluation)
        baker.make(UserProfile, email="contributor1@institution.example.com", contributions=[contribution1])
        contributor2 = baker.make(
            UserProfile, email="contributor2@institution.example.com", contributions=[contribution2]
        )
        testuser1.cc_users.set([contributor2])

        expected_users = set(UserProfile.objects.exclude(email="testuser2@institution.example.com"))

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-bulk-update-form"]
        form["user_file"] = (self.filename,)
        response = form.submit(name="operation", value="test")

        self.assertIn(
            "1 will be updated, 1 will be deleted and 1 will be marked inactive. 1 new users will be created.", response
        )
        self.assertIn("testupdate@institution.example.com &gt; testupdate@internal.example.com", response)
        self.assertIn(mock_remove.return_value[0], response)
        self.assertEqual(mock_remove.call_count, 2)
        calls = [[call[0][0].email, call[0][2]] for call in mock_remove.call_args_list]
        self.assertEqual(calls, [[testuser2.email, True], [contributor2.email, True]])
        mock_remove.reset_mock()

        form = response.forms["user-bulk-update-form"]
        response = form.submit(name="operation", value="bulk_update").follow()

        # testuser1 is in the file and must not be deleted
        self.assertTrue(UserProfile.objects.filter(email="testuser1@institution.example.com").exists())
        # testuser2 is not in the file and must be deleted
        self.assertFalse(UserProfile.objects.filter(email="testuser2@institution.example.com").exists())
        # manager is not in the file but still must not be deleted
        self.assertTrue(UserProfile.objects.filter(email="manager@institution.example.com").exists())
        # testusernewinternal is a new internal user and should be created
        self.assertTrue(UserProfile.objects.filter(email="testusernewinternal@institution.example.com").exists())
        expected_users.add(UserProfile.objects.get(email="testusernewinternal@institution.example.com"))
        # testusernewexternal is an external user and should not be created
        self.assertFalse(UserProfile.objects.filter(email="testusernewexternal@example.com").exists())
        # testupdate should have been renamed
        self.assertFalse(UserProfile.objects.filter(email="testupdate@institution.example.com").exists())
        self.assertTrue(UserProfile.objects.filter(email="testupdate@internal.example.com").exists())

        # contributor1 should still be active, contributor2 should have been set to inactive
        self.assertTrue(UserProfile.objects.get(email="contributor1@institution.example.com").is_active)
        self.assertFalse(UserProfile.objects.get(email="contributor2@institution.example.com").is_active)
        # all should be active except for contributor2
        self.assertEqual(UserProfile.objects.filter(is_active=True).count(), len(expected_users) - 1)

        self.assertEqual(set(UserProfile.objects.all()), expected_users)

        # mock gets called for every user to be deleted (once for the test run and once for the real run)
        self.assertIn(mock_remove.return_value[0], response)
        self.assertEqual(mock_remove.call_count, 2)
        calls = [[call[0][0].email, call[0][2]] for call in mock_remove.call_args_list]
        self.assertEqual(calls, [[testuser2.email, False], [contributor2.email, False]])

    @override_settings(DEBUG=False)
    def test_wrong_files_dont_crash(self):
        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-bulk-update-form"]
        form["user_file"] = ("import.xls", self.random_excel_file_content)
        reply = form.submit(name="operation", value="test", status=200)
        self.assertIn("An error happened when processing the file", reply)

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-bulk-update-form"]
        form["user_file"] = (
            "test_enrollment_data.xls",
            excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata),
        )
        reply = form.submit(name="operation", value="test", status=200)
        self.assertIn("An error happened when processing the file", reply)


class TestUserExportView(WebTestStaffMode):
    url = reverse("staff:user_export")

    @classmethod
    def setUpTestData(cls) -> None:
        cls.manager = make_manager()
        # titles are not filled by baker because it has a default, see https://github.com/model-bakers/model_bakery/discussions/346
        baker.make(
            UserProfile,
            _quantity=5,
            _fill_optional=["first_name_given", "last_name", "email"],
            title=iter(("", "Some", "Custom", "Titles", "")),
        )

    def test_export_all(self):
        user_objects = {
            (user.title or "", user.last_name or "", user.first_name or "", user.email or "")
            for user in UserProfile.objects.iterator()
        }
        response = self.app.get(self.url, user=self.manager)

        reader = csv.reader(response.text.strip().split("\n"), delimiter=";", lineterminator="\n")
        # skip header
        next(reader)
        self.assertEqual({tuple(row) for row in reader}, user_objects)


class TestUserImportView(WebTestStaffMode):
    url = "/staff/user/import"

    @classmethod
    def setUpTestData(cls):
        cls.valid_excel_file_content = excel_data.create_memory_excel_file(excel_data.valid_user_import_filedata)
        cls.missing_values_excel_file_content = excel_data.create_memory_excel_file(
            excel_data.missing_values_user_import_filedata
        )
        cls.random_excel_file_content = excel_data.random_file_content

        cls.manager = make_manager()

    @render_pages
    def render_pages(self):
        return {
            "normal": self.app.get(self.url, user=self.manager).content,
        }

    def test_success_handling(self):
        """
        Tests whether a correct excel file is correctly tested and imported and whether the success messages are displayed
        """
        page = self.app.get(self.url, user=self.manager)
        form = page.forms["user-import-form"]
        form["excel_file"] = ("import.xls", self.valid_excel_file_content)
        page = form.submit(name="operation", value="test")

        self.assertContains(
            page,
            "The import run will create 2 users:<br />"
            "Lucilia Manilium (lucilia.manilium@institution.example.com)<br />"
            "Bastius Quid (bastius.quid@external.example.com)",
        )
        self.assertContains(page, "Import previously uploaded file")

        form = page.forms["user-import-form"]
        submit_with_modal(page, form, name="operation", value="import")

        page = self.app.get(self.url, user=self.manager)
        self.assertNotContains(page, "Import previously uploaded file")

    def test_error_handling(self):
        """
        Tests whether errors given from the importer are displayed
        """
        page = self.app.get(self.url, user=self.manager)

        original_user_count = UserProfile.objects.count()

        form = page.forms["user-import-form"]
        form["excel_file"] = ("import.xls", self.missing_values_excel_file_content)

        reply = form.submit(name="operation", value="test")

        self.assertContains(
            reply,
            "Sheet &quot;Sheet 1&quot;, row 2: User missing.firstname@institution.example.com: First name is missing.",
        )
        self.assertContains(
            reply,
            "Sheet &quot;Sheet 1&quot;, row 3: User missing.lastname@institution.example.com: Last name is missing.",
        )
        self.assertContains(reply, "Sheet &quot;Sheet 1&quot;, row 4: Email address is missing.")
        self.assertContains(reply, "Errors occurred while parsing the input data. No data was imported.")
        self.assertNotContains(reply, "Import previously uploaded file")

        self.assertEqual(UserProfile.objects.count(), original_user_count)

    def test_warning_handling(self):
        """
        Tests whether warnings given from the importer are displayed
        """
        user = baker.make(UserProfile, email="lucilia.manilium@institution.example.com")

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-import-form"]
        form["excel_file"] = ("import.xls", self.valid_excel_file_content)

        reply = form.submit(name="operation", value="test")

        self.assertContains(reply, "Name mismatches")
        self.assertContains(
            reply,
            "The existing user would be overwritten with the following data:<br />"
            f" -  (empty) (empty), lucilia.manilium@institution.example.com [{user_edit_link(user.pk)}] (existing)<br />"
            " -  Lucilia Manilium, lucilia.manilium@institution.example.com (import)",
        )

        helper_delete_all_import_files(self.manager.id)

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-import-form"]
        form["excel_file"] = ("import.xls", self.valid_excel_file_content)

        form.submit(name="operation", value="hackit", status=400)

    def test_invalid_upload_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-import-form"]
        page = form.submit(name="operation", value="test")

        self.assertContains(page, "This field is required.")
        self.assertNotContains(page, "Import previously uploaded file")

    def test_invalid_import_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["user-import-form"]
        form.submit(name="operation", value="import", status=400)


# Staff - Semester Views
class TestSemesterView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.url = f"/staff/semester/{cls.semester.pk}"

        baker.make(
            Evaluation,
            name_de="Evaluation 1",
            name_en="Evaluation 1",
            course=baker.make(Course, name_de="A", name_en="B", semester=cls.semester),
        )
        baker.make(
            Evaluation,
            name_de="Evaluation 2",
            name_en="Evaluation 2",
            course=baker.make(Course, name_de="B", name_en="A", semester=cls.semester),
        )

    def test_view_list_sorting(self):
        self.manager.language = "de"
        self.manager.save()
        page = self.app.get(self.url, user=self.manager).body.decode("utf-8")
        position_evaluation1 = page.find("Evaluation 1")
        position_evaluation2 = page.find("Evaluation 2")
        self.assertLess(position_evaluation1, position_evaluation2)
        self.app.reset()  # language is only loaded on login, so we're forcing a re-login here

        # Re-enter staff mode, since the session was just reset
        with run_in_staff_mode(self):
            self.manager.language = "en"
            self.manager.save()
            page = self.app.get(self.url, user=self.manager).body.decode("utf-8")
            position_evaluation1 = page.find("Evaluation 1")
            position_evaluation2 = page.find("Evaluation 2")
            self.assertGreater(position_evaluation1, position_evaluation2)

    def test_access_to_semester_with_archived_results(self):
        reviewer = baker.make(
            UserProfile,
            email="reviewer@institution.example.com",
            groups=[Group.objects.get(name="Reviewer")],
        )
        semester = baker.make(Semester, results_are_archived=True)

        # managers can access the page
        self.app.get(f"/staff/semester/{semester.pk}", user=self.manager, status=200)

        # reviewers shouldn't be allowed to access the semester page
        self.app.get(f"/staff/semester/{semester.pk}", user=reviewer, status=403)

    @override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com"])
    def test_badge_for_external_responsibles(self):
        responsible = baker.make(UserProfile, email="a@institution.com")
        course = baker.make(Course, semester=self.semester, responsibles=[responsible])
        baker.make(Evaluation, course=course)
        response = self.app.get(self.url, user=self.manager)
        self.assertNotContains(response, "External responsible")

        responsible.email = "r@external.com"
        responsible.save()
        response = self.app.get(self.url, user=self.manager)
        self.assertContains(response, "External responsible")

    @patch("evap.evaluation.models.Evaluation.textanswer_review_state", new_callable=PropertyMock)
    def test_textanswer_review_state_tags(self, textanswer_review_state_mock):
        """Regression test for #1465"""

        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            can_publish_text_results=True,
            course__semester=self.semester,
        )
        baker.make(TextAnswer, contribution=evaluation.general_contribution)

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.NO_TEXTANSWERS
        page = self.app.get(f"/staff/semester/{evaluation.course.semester.id}", user=self.manager)
        expected_count = page.body.decode().count("no_review")

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.NO_REVIEW_NEEDED
        page = self.app.get(f"/staff/semester/{evaluation.course.semester.id}", user=self.manager)
        self.assertEqual(page.body.decode().count("no_review"), expected_count)

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.REVIEW_NEEDED
        page = self.app.get(f"/staff/semester/{evaluation.course.semester.id}", user=self.manager)
        # + 1 because the buttons at the top of the page contain it two times (once for _urgent)
        self.assertEqual(page.body.decode().count("unreviewed_textanswers"), expected_count + 1)
        self.assertEqual(page.body.decode().count("no_review"), 1)

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.REVIEW_URGENT
        page = self.app.get(f"/staff/semester/{evaluation.course.semester.id}", user=self.manager)
        self.assertEqual(page.body.decode().count("unreviewed_textanswers_urgent"), expected_count)
        self.assertEqual(page.body.decode().count("no_review"), 1)

        textanswer_review_state_mock.return_value = Evaluation.TextAnswerReviewState.REVIEWED
        page = self.app.get(f"/staff/semester/{evaluation.course.semester.id}", user=self.manager)
        self.assertEqual(page.body.decode().count("textanswers_reviewed"), expected_count)
        self.assertEqual(page.body.decode().count("no_review"), 1)


class TestGetEvaluationsWithPrefetchedData(TestCase):
    @staticmethod
    def test_get_evaluations_with_prefetched_data():
        evaluation = baker.make(Evaluation, is_single_result=True)
        get_evaluations_with_prefetched_data(evaluation.course.semester)


class TestSemesterCreateView(WebTestStaffMode):
    url = "/staff/semester/create"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_create(self):
        name_de = "name_de"
        short_name_de = "short_name_de"
        name_en = "name_en"
        short_name_en = "short_name_en"

        response = self.app.get(self.url, user=self.manager)
        form = response.forms["semester-form"]
        form["name_de"] = name_de
        form["short_name_de"] = short_name_de
        form["name_en"] = name_en
        form["short_name_en"] = short_name_en
        form.submit()

        self.assertEqual(
            Semester.objects.filter(
                name_de=name_de, name_en=name_en, short_name_de=short_name_de, short_name_en=short_name_en
            ).count(),
            1,
        )


class TestSemesterEditView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, name_de="old_name", name_en="old_name")
        cls.url = f"/staff/semester/{cls.semester.pk}/edit"

    def test_name_change(self):
        new_name_de = "new_name_de"
        new_name_en = "new_name_en"
        self.assertNotEqual(self.semester.name_de, new_name_de)
        self.assertNotEqual(self.semester.name_en, new_name_en)

        response = self.app.get(self.url, user=self.manager)
        form = response.forms["semester-form"]
        form["name_de"] = new_name_de
        form["name_en"] = new_name_en
        form.submit()

        self.semester.refresh_from_db()
        self.assertEqual(self.semester.name_de, new_name_de)
        self.assertEqual(self.semester.name_en, new_name_en)


class TestSemesterDeleteView(DeleteViewTestMixin, WebTestStaffMode):
    url = reverse("staff:semester_delete")
    model_cls = Semester
    permission_method_to_patch = (Semester, "can_be_deleted_by_manager")

    @classmethod
    def get_post_params(cls):
        return {"semester_id": cls.instance.pk}

    def test_success_with_data(self):
        evaluation = baker.make(Evaluation, course__semester=self.instance, state=Evaluation.State.PUBLISHED)
        responsible_contribution = baker.make(Contribution, evaluation=evaluation, contributor=baker.make(UserProfile))
        baker.make(RatingAnswerCounter, contribution=responsible_contribution)
        baker.make(
            TextAnswer,
            contribution=evaluation.general_contribution,
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )

        self.instance.archive()
        self.instance.delete_grade_documents()
        self.instance.archive_results()
        self.app.post(self.url, params=self.post_params, user=self.user)

        self.assertFalse(Semester.objects.filter(pk=self.instance.pk).exists())


class TestSemesterAssignView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.url = f"/staff/semester/{cls.semester.pk}/assign"

        lecture_type = baker.make(CourseType, name_de="Vorlesung", name_en="Lecture")
        seminar_type = baker.make(CourseType, name_de="Seminar", name_en="Seminar")
        cls.questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)

        evaluation1 = baker.make(Evaluation, course__type=seminar_type, course__semester=cls.semester)
        evaluation2 = baker.make(Evaluation, course__type=lecture_type, course__semester=cls.semester)
        baker.make(
            Contribution,
            contributor=baker.make(UserProfile),
            evaluation=iter([evaluation1, evaluation2]),
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            _fill_optional=["contributor"],
            _quantity=2,
            _bulk_create=True,
        )

    def test_assign_questionnaires(self):
        page = self.app.get(self.url, user=self.manager)
        assign_form = page.forms["questionnaire-assign-form"]
        assign_form["Seminar"] = [self.questionnaire.pk]
        assign_form["Lecture"] = [self.questionnaire.pk]
        page = assign_form.submit().follow()

        for evaluation in self.semester.evaluations.all():
            self.assertEqual(evaluation.general_contribution.questionnaires.count(), 1)
            self.assertEqual(evaluation.general_contribution.questionnaires.get(), self.questionnaire)


class TestSemesterPreparationReminderView(WebTestStaffModeWith200Check):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)

        cls.url = f"/staff/semester/{cls.semester.pk}/preparation_reminder"
        cls.test_users = [cls.manager]

    def test_preparation_reminder(self):
        user = baker.make(UserProfile, email="user_to_find@institution.example.com")
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, semester=self.semester, responsibles=[user]),
            state=Evaluation.State.PREPARED,
            name_en="name_to_find",
            name_de="name_to_find",
        )
        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=user,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )

        response = self.app.get(self.url, user=self.manager)
        self.assertContains(response, "user_to_find")
        self.assertContains(response, "name_to_find")

    @patch("evap.staff.views.EmailTemplate")
    def test_remind_all(self, email_template_mock):
        user = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, semester=self.semester, responsibles=[user]),
            state=Evaluation.State.PREPARED,
        )

        email_template_mock.objects.get.return_value = email_template_mock
        email_template_mock.EDITOR_REVIEW_REMINDER = EmailTemplate.EDITOR_REVIEW_REMINDER

        self.app.post(self.url, user=self.manager, status=200)

        subject_params = {}
        body_params = {"user": user, "evaluations": [evaluation]}
        expected = (user, subject_params, body_params)

        email_template_mock.send_to_user.assert_called_once()
        self.assertEqual(email_template_mock.send_to_user.call_args_list[0][0][:4], expected)


class TestGradeReminderView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.responsible = baker.make(UserProfile, first_name_given="Bastius", last_name="Quid")
        cls.evaluation = baker.make(
            Evaluation,
            course__name_en="How to make a sandwich",
            course__responsibles=[cls.responsible],
            course__gets_no_grade_documents=False,
            state=Evaluation.State.EVALUATED,
            wait_for_grade_upload_before_publishing=True,
        )
        cls.url = f"/staff/semester/{cls.evaluation.course.semester.pk}/grade_reminder"

    def test_reminders_are_shown(self):
        page = self.app.get(self.url, user=self.manager)

        self.assertContains(page, "Bastius Quid")
        self.assertContains(page, "How to make a sandwich")


class TestSendReminderView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        responsible = baker.make(UserProfile, email="a.b@example.com")
        evaluation = baker.make(Evaluation, course__responsibles=[responsible], state=Evaluation.State.PREPARED)
        cls.url = f"/staff/semester/{evaluation.course.semester.pk}/responsible/{responsible.pk}/send_reminder"

    def test_form(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["send-reminder-form"]
        form["plain_content"] = "uiae"
        form["html_content"] = "<p>uiae</p>"
        form.submit()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("uiae", mail.outbox[0].body)


class TestSemesterArchiveParticipationsView(WebTestStaffMode):
    csrf_checks = False
    url = reverse("staff:semester_archive_participations")

    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester)
        cls.manager = make_manager()

    @patch.object(Semester, "participations_can_be_archived", True)
    @patch.object(Semester, "archive")
    def test_valid_archivation(self, archive_mock):
        self.app.post(self.url, user=self.manager, params={"semester_id": self.semester.pk})
        archive_mock.assert_called_once()

    @patch.object(Semester, "participations_can_be_archived", False)
    @patch.object(Semester, "archive")
    def test_invalid_archivation(self, archive_mock):
        self.app.post(self.url, user=self.manager, params={"semester_id": self.semester.pk}, status=400)
        archive_mock.assert_not_called()


class TestSemesterDeleteGradeDocumentsView(DeleteViewTestMixin, WebTestStaffMode):
    url = reverse("staff:semester_delete_grade_documents")
    model_cls = GradeDocument
    permission_method_to_patch = (Semester, "grade_documents_can_be_deleted")

    @classmethod
    def get_post_params(cls):
        return {"semester_id": cls.instance.course.semester.pk}


class TestSemesterImportView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.random_excel_file_content = excel_data.random_file_content

        cls.manager = make_manager()
        semester = baker.make(Semester)
        cls.url = f"/staff/semester/{semester.pk}/import"

        baker.make(CourseType, name_de="Vorlesung", name_en="Lecture", import_names=["Vorlesung"])
        baker.make(CourseType, name_de="Seminar", name_en="Seminar", import_names=["Seminar"])

    def test_import_valid_file(self):
        original_user_count = UserProfile.objects.count()

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        form["excel_file"] = (
            "test_enrollment_data.xls",
            excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata),
        )
        page = form.submit(name="operation", value="test")

        self.assertEqual(UserProfile.objects.count(), original_user_count)

        form = page.forms["semester-import-form"]
        form["vote_start_datetime"] = "2000-01-01 00:00:00"
        form["vote_end_date"] = "2012-01-01"
        submit_with_modal(page, form, name="operation", value="import")

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
        form["excel_file"] = (
            "invalid_enrollment_data.xls",
            excel_data.create_memory_excel_file(excel_data.invalid_enrollment_data_filedata),
        )

        reply = form.submit(name="operation", value="test")
        general_error = "Errors occurred while parsing the input data. No data was imported."
        self.assertContains(reply, general_error)
        degree_error = (
            "Sheet &quot;MA Belegungen&quot;, row 8 and 1 other place: "
            "No degree is associated with the import name &quot;Diploma&quot;. "
            "Please manually create it first."
        )
        self.assertContains(reply, degree_error)
        course_type_error = (
            "Sheet &quot;MA Belegungen&quot;, row 11 and 1 other place: "
            "No course type is associated with the import name &quot;Praktikum&quot;. "
            "Please manually create it first."
        )
        self.assertContains(reply, course_type_error)
        is_graded_error = (
            "Sheet &quot;MA Belegungen&quot;, row 5: &quot;is_graded&quot; is maybe, but must be yes or no"
        )
        self.assertContains(reply, is_graded_error)
        user_error = (
            "Sheet &quot;MA Belegungen&quot;, row 3: The data of user"
            " &quot;bastius.quid@external.example.com&quot; differs from their data in a previous row."
        )
        self.assertContains(reply, user_error)
        self.assertContains(reply, "Sheet &quot;MA Belegungen&quot;, row 7: Email address is missing.")
        self.assertContains(reply, "Sheet &quot;MA Belegungen&quot;, row 10: Email address is missing.")

        def index(text):
            return reply.body.decode().index(text)

        self.assertTrue(
            index(general_error)
            < index(degree_error)
            < index(course_type_error)
            < index(is_graded_error)
            < index(user_error)
        )

        self.assertNotContains(reply, "Import previously uploaded file")

    def test_warning_handling(self):
        """
        Tests whether warnings given from the importer are displayed
        """
        user = baker.make(UserProfile, email="lucilia.manilium@institution.example.com")

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        form["excel_file"] = (
            "test_enrollment_data.xls",
            excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata),
        )

        reply = form.submit(name="operation", value="test")
        self.assertContains(reply, "Name mismatches")
        self.assertContains(
            reply,
            "The existing user would be overwritten with the following data:<br />"
            f" -  (empty) (empty), lucilia.manilium@institution.example.com [{user_edit_link(user.pk)}] (existing)<br />"
            " -  Lucilia Manilium, lucilia.manilium@institution.example.com (import)",
        )
        helper_delete_all_import_files(self.manager.id)

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        form["excel_file"] = (
            "test_enrollment_data.xls",
            excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata),
        )

        form.submit(name="operation", value="hackit", status=400)

    def test_invalid_upload_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        page = form.submit(name="operation", value="test")

        self.assertContains(page, "This field is required.")
        self.assertNotContains(page, "Import previously uploaded file")

    def test_invalid_import_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        form.submit(name="operation", value="import", status=400)

    def test_missing_evaluation_period(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["semester-import-form"]
        form["excel_file"] = (
            "test_enrollment_data.xls",
            excel_data.create_memory_excel_file(excel_data.test_enrollment_data_filedata),
        )
        page = form.submit(name="operation", value="test")

        page = submit_with_modal(page, page.forms["semester-import-form"], name="operation", value="import")

        self.assertContains(page, "This field is required.")
        self.assertContains(page, "Import previously uploaded file")
        helper_delete_all_import_files(self.manager.id)


class TestSemesterExportView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.degree = baker.make(Degree)
        evaluation = baker.make(Evaluation, course__degrees=[cls.degree])
        cls.semester = evaluation.course.semester
        cls.course_type = evaluation.course.type
        cls.url = f"/staff/semester/{cls.semester.pk}/export"

    def test_view_downloads_excel_file(self):
        page = self.app.get(self.url, user=self.manager)
        form = page.forms["semester-export-form"]

        # Check one degree and course type.
        form.set("form-0-selected_degrees", "id_form-0-selected_degrees_0")
        form.set("form-0-selected_course_types", "id_form-0-selected_course_types_0")

        response = form.submit()

        # Load response as Excel file and check its heading for correctness.
        workbook = xlrd.open_workbook(file_contents=response.content)
        self.assertEqual(
            workbook.sheets()[0].row_values(0)[0],
            f"Evaluation\n{self.semester.name}\n\n{self.degree.name}\n\n{self.course_type.name}",
        )


class TestSemesterRawDataExportView(WebTestStaffModeWith200Check):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.course_type = baker.make(CourseType, name_en="Type")

        cls.url = f"/staff/semester/{cls.semester.pk}/raw_export"
        cls.test_users = [cls.manager]

    def test_view_downloads_csv_file(self):
        student_user = baker.make(UserProfile, email="student@institution.example.com")
        baker.make(
            Evaluation,
            course=baker.make(Course, type=self.course_type, semester=self.semester, name_de="1", name_en="Course 1"),
            participants=[student_user],
            voters=[student_user],
            name_de="E1",
            name_en="E1",
        )
        baker.make(
            Evaluation,
            course=baker.make(Course, type=self.course_type, semester=self.semester, name_de="2", name_en="Course 2"),
            participants=[student_user],
        )

        response = self.app.get(self.url, user=self.manager)
        expected_content = (
            "Name;Degrees;Type;Single result;State;#Voters;#Participants;#Text answers;Average grade\n"
            "Course 1 – E1;;Type;False;new;1;1;0;\n"
            "Course 2;;Type;False;new;0;1;0;\n"
        )
        self.assertEqual(response.content, expected_content.encode("utf-8"))

    def test_single_result(self):
        baker.make(
            Evaluation,
            course=baker.make(
                Course, type=self.course_type, semester=self.semester, name_de="3", name_en="Single Result"
            ),
            _participant_count=5,
            _voter_count=5,
            is_single_result=True,
        )

        response = self.app.get(self.url, user=self.manager)
        expected_content = (
            "Name;Degrees;Type;Single result;State;#Voters;#Participants;#Text answers;Average grade\n"
            "Single Result;;Type;True;new;5;5;0;\n"
        )
        self.assertEqual(response.content, expected_content.encode("utf-8"))


class TestSemesterParticipationDataExportView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        student_user = baker.make(UserProfile, email="student@example.com")
        student_user2 = baker.make(UserProfile, email="student2@example.com")

        semester = baker.make(Semester)
        cls.url = f"/staff/semester/{semester.pk}/participation_export"

        baker.make(
            Evaluation,
            course__semester=semester,
            participants=[student_user],
            voters=[student_user],
            _fill_optional=["name_de", "name_en"],
            is_rewarded=True,
        )
        baker.make(
            Evaluation,
            course__semester=semester,
            participants=[student_user, student_user2],
            _fill_optional=["name_de", "name_en"],
            is_rewarded=False,
        )
        baker.make(RewardPointGranting, semester=semester, user_profile=student_user, value=23)
        baker.make(RewardPointGranting, semester=semester, user_profile=student_user, value=42)

    def test_view_downloads_csv_file(self):
        response = self.app.get(self.url, user=self.manager)
        expected_content = (
            "Email;Can use reward points;#Required evaluations voted for;#Required evaluations;#Optional evaluations voted for;"
            "#Optional evaluations;Earned reward points\n"
            "student2@example.com;False;0;0;0;1;0\n"
            "student@example.com;False;1;1;0;1;65\n"
        )
        self.assertEqual(response.content, expected_content.encode("utf-8"))


class TestSemesterVoteTimestampsExport(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.course_type = baker.make(CourseType, name_en="Type")
        cls.vote_end_date = datetime.date(2017, 1, 3)
        cls.evaluation_id = 1
        cls.timestamp_time = datetime.datetime(2017, 1, 1, 12, 0, 0)

        cls.evaluation = baker.make(
            Evaluation,
            course__type=cls.course_type,
            pk=cls.evaluation_id,
            vote_end_date=cls.vote_end_date,
            vote_start_datetime=datetime.datetime.combine(cls.vote_end_date, datetime.time())
            - datetime.timedelta(days=2),
        )
        cls.timestamp = baker.make(VoteTimestamp, evaluation=cls.evaluation, timestamp=cls.timestamp_time)

    def test_view_downloads_csv_file(self):
        response = self.app.get(
            reverse("staff:vote_timestamps_export", args=[self.evaluation.course.semester.pk]), user=self.manager
        )
        expected_content = (
            "Evaluation id;Course type;Course degrees;Vote end date;Timestamp\n"
            f"{self.evaluation_id};Type;;{self.vote_end_date};{self.timestamp_time}\n"
        ).encode()
        self.assertEqual(response.content, expected_content)


class TestLoginKeyExportView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.external_user = baker.make(UserProfile, email="user@external.com")
        cls.internal_user = baker.make(UserProfile, email="user@institution.example.com")

        evaluation = baker.make(
            Evaluation,
            participants=[cls.external_user, cls.internal_user],
            voters=[cls.external_user, cls.internal_user],
        )
        cls.url = reverse("staff:evaluation_login_key_export", args=[evaluation.pk])

    def test_login_key_export_works_as_expected(self):
        self.assertEqual(self.external_user.login_key, None)
        self.assertEqual(self.internal_user.login_key, None)

        response = self.app.get(self.url, user=self.manager)

        self.external_user.refresh_from_db()
        self.assertNotEqual(self.external_user.login_key, None)
        self.assertEqual(self.internal_user.login_key, None)

        expected_string = f"Last name;First name;Email;Login key\n;;user@external.com;localhost:8000/key/{self.external_user.login_key}\n"
        self.assertEqual(response.body.decode(), expected_string)


class TestEvaluationOperationView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.responsible = baker.make(UserProfile, email="responsible@example.com")
        cls.course = baker.make(Course, semester=cls.semester, responsibles=[cls.responsible])
        cls.url = reverse("staff:evaluation_operation", args=[cls.semester.pk])

    def helper_publish_evaluation_with_publish_notifications_for(
        self, evaluation, contributors=True, participants=True
    ):
        page = self.app.get(f"/staff/semester/{self.semester.pk}", user=self.manager)
        form = page.forms["evaluation_operation_form"]
        form["evaluation"] = evaluation.pk
        response = form.submit("target_state", value=str(Evaluation.State.PUBLISHED))

        form = response.forms["evaluation-operation-form"]
        form["send_email_contributor"] = contributors
        form["send_email_participant"] = participants
        form.submit()

        evaluation = evaluation.course.semester.evaluations.first()
        evaluation.unpublish()
        evaluation.save()

    def test_publish_notifications(self):
        participant1 = baker.make(UserProfile, email="foo@example.com")
        participant2 = baker.make(UserProfile, email="bar@example.com")
        contributor1 = baker.make(UserProfile, email="contributor@example.com")

        evaluation = baker.make(
            Evaluation,
            course=self.course,
            state=Evaluation.State.REVIEWED,
            participants=[participant1, participant2],
            voters=[participant1, participant2],
        )
        baker.make(Contribution, contributor=contributor1, evaluation=evaluation)
        cache_results(evaluation)

        self.helper_publish_evaluation_with_publish_notifications_for(
            evaluation, contributors=False, participants=False
        )
        self.assertEqual(len(mail.outbox), 0)
        mail.outbox = []

        self.helper_publish_evaluation_with_publish_notifications_for(evaluation, contributors=True, participants=False)
        self.assertEqual(len(mail.outbox), 2)
        self.assertCountEqual([[contributor1.email], [self.responsible.email]], [mail.outbox[0].to, mail.outbox[1].to])
        mail.outbox = []

        self.helper_publish_evaluation_with_publish_notifications_for(evaluation, contributors=False, participants=True)
        self.assertEqual(len(mail.outbox), 2)
        self.assertCountEqual([[participant1.email], [participant2.email]], [mail.outbox[0].to, mail.outbox[1].to])
        mail.outbox = []

        self.helper_publish_evaluation_with_publish_notifications_for(evaluation, contributors=True, participants=True)
        self.assertEqual(len(mail.outbox), 4)
        self.assertCountEqual(
            [[participant1.email], [participant2.email], [contributor1.email], [self.responsible.email]],
            [outbox_entry.to for outbox_entry in mail.outbox],
        )
        mail.outbox = []

    def helper_semester_state_views(self, evaluation, old_state, new_state):
        """Used with the tests below to ensure evaluation state transitions can be triggered in the UI"""

        page = self.app.get(f"/staff/semester/{self.semester.pk}", user=self.manager)
        form = page.forms["evaluation_operation_form"]
        self.assertEqual(evaluation.state, old_state)
        form["evaluation"] = evaluation.pk
        response = form.submit("target_state", value=str(new_state))

        form = response.forms["evaluation-operation-form"]
        response = form.submit().follow()
        self.assertIn("Successfully", str(response))
        self.assertEqual(Evaluation.objects.get(pk=evaluation.pk).state, new_state)

    def test_semester_publish(self):
        participant1 = baker.make(UserProfile, email="foo@example.com")
        participant2 = baker.make(UserProfile, email="bar@example.com")
        evaluation = baker.make(
            Evaluation,
            course=self.course,
            state=Evaluation.State.REVIEWED,
            participants=[participant1, participant2],
            voters=[participant1, participant2],
        )
        cache_results(evaluation)

        self.helper_semester_state_views(evaluation, Evaluation.State.REVIEWED, Evaluation.State.PUBLISHED)
        self.assertEqual(len(mail.outbox), 3)
        self.assertCountEqual(
            [[participant1.email], [participant2.email], [self.responsible.email]],
            [outbox_entry.to for outbox_entry in mail.outbox],
        )

    def test_semester_reset_1(self):
        evaluation = baker.make(Evaluation, course=self.course, state=Evaluation.State.PREPARED)
        self.helper_semester_state_views(evaluation, Evaluation.State.PREPARED, Evaluation.State.NEW)

    def test_semester_reset_2(self):
        evaluation = baker.make(Evaluation, course=self.course, state=Evaluation.State.APPROVED)
        self.helper_semester_state_views(evaluation, Evaluation.State.APPROVED, Evaluation.State.NEW)

    def test_semester_contributor_ready_1(self):
        evaluation = baker.make(Evaluation, course=self.course, state=Evaluation.State.NEW)
        self.helper_semester_state_views(evaluation, Evaluation.State.NEW, Evaluation.State.PREPARED)

    def test_semester_contributor_ready_2(self):
        evaluation = baker.make(Evaluation, course=self.course, state=Evaluation.State.EDITOR_APPROVED)
        self.helper_semester_state_views(evaluation, Evaluation.State.EDITOR_APPROVED, Evaluation.State.PREPARED)

    def test_semester_unpublish(self):
        evaluation = baker.make(
            Evaluation, course=self.course, state=Evaluation.State.PUBLISHED, _participant_count=0, _voter_count=0
        )
        self.helper_semester_state_views(evaluation, Evaluation.State.PUBLISHED, Evaluation.State.REVIEWED)

    def test_operation_start_evaluation(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.APPROVED, course=self.course)
        urloptions = f"?evaluation={evaluation.pk}&target_state={Evaluation.State.IN_EVALUATION}"

        response = self.app.get(self.url + urloptions, user=self.manager, status=200)
        form = response.forms["evaluation-operation-form"]
        form.submit()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, Evaluation.State.IN_EVALUATION)

    def test_operation_prepare(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.NEW, course=self.course)
        urloptions = f"?evaluation={evaluation.pk}&target_state={Evaluation.State.PREPARED}"

        response = self.app.get(self.url + urloptions, user=self.manager, status=200)
        form = response.forms["evaluation-operation-form"]
        form.submit()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, Evaluation.State.PREPARED)

    def submit_operation_prepare_form(self, url_options):
        actual_emails = []

        def mock(email_template, user, subject_params, body_params, use_cc, additional_cc_users=None, request=None):
            actual_emails.append(
                {
                    "user": user,
                    "subject": email_template.subject,
                    "subject_params": subject_params,
                    "plain_content": email_template.plain_content,
                    "body_params": body_params,
                    "html_content": email_template.html_content,
                    "use_cc": use_cc,
                    "additional_cc_users": set(additional_cc_users),
                }
            )

        response = self.app.get(self.url + url_options, user=self.manager)
        form = response.forms["evaluation-operation-form"]
        form["send_email"] = True
        form["email_subject"] = "New evaluations ready for review"
        form["email_plain"] = "There are evaluations that need your approval."
        form["email_html"] = "<p>There are evaluations that need your approval.</p>"

        with patch.object(EmailTemplate, "send_to_user", mock):
            form.submit()

        return actual_emails

    def test_operation_prepare_sends_email_to_responsible(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.NEW, course=self.course)
        url_options = f"?evaluation={evaluation.pk}&target_state={Evaluation.State.PREPARED}"
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(
            actual_emails,
            [
                {
                    "user": self.responsible,
                    "subject": "New evaluations ready for review",
                    "subject_params": {},
                    "plain_content": "There are evaluations that need your approval.",
                    "body_params": {"user": self.responsible, "evaluations": [evaluation]},
                    "html_content": "<p>There are evaluations that need your approval.</p>",
                    "use_cc": True,
                    "additional_cc_users": set(),
                }
            ],
        )

    def test_operation_prepare_sends_one_email_to_each_responsible(self):
        other_responsible = baker.make(UserProfile, email="co-responsible@example.com")
        self.course.responsibles.add(other_responsible)
        evaluation = baker.make(Evaluation, state=Evaluation.State.NEW, course=self.course)
        url_options = f"?evaluation={evaluation.pk}&target_state={Evaluation.State.PREPARED}"
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 2)

        email_to_responsible = next(email for email in actual_emails if email["user"] == self.responsible)
        self.assertEqual(email_to_responsible["body_params"], {"user": self.responsible, "evaluations": [evaluation]})

        email_to_other_responsible = next(email for email in actual_emails if email["user"] == other_responsible)
        self.assertEqual(
            email_to_other_responsible["body_params"], {"user": other_responsible, "evaluations": [evaluation]}
        )

    def test_operation_prepare_with_multiple_evaluations(self):
        responsible_b = baker.make(UserProfile, email="responsible-b@example.com")
        course_b = baker.make(Course, semester=self.semester, responsibles=[responsible_b])
        evaluation_a = baker.make(Evaluation, state=Evaluation.State.NEW, course=self.course)
        evaluation_b = baker.make(Evaluation, state=Evaluation.State.NEW, course=course_b)
        url_options = (
            f"?evaluation={evaluation_a.pk}&evaluation={evaluation_b.pk}&target_state={Evaluation.State.PREPARED}"
        )
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 2)

        email_to_responsible = next(email for email in actual_emails if email["user"] == self.responsible)
        self.assertEqual(email_to_responsible["body_params"], {"user": self.responsible, "evaluations": [evaluation_a]})

        email_to_responsible_b = next(email for email in actual_emails if email["user"] == responsible_b)
        self.assertEqual(email_to_responsible_b["body_params"], {"user": responsible_b, "evaluations": [evaluation_b]})

    def test_operation_prepare_with_no_applicable_evaluations(self):
        evaluation1 = baker.make(Evaluation, state=Evaluation.State.REVIEWED, course__semester=self.semester)
        evaluation2 = baker.make(Evaluation, state=Evaluation.State.NEW, course__semester=self.semester)

        # No evaluations at all
        url_options = f"?target_state={Evaluation.State.PREPARED}"
        response = self.app.get(self.url + url_options, user=self.manager).follow()
        self.assertContains(response, "Please select at least one evaluation")

        # No evaluations that the operation could be applied on
        url_options = f"?evaluation={evaluation1.pk}&target_state={Evaluation.State.PREPARED}"
        response = self.app.get(self.url + url_options, user=self.manager).follow()
        self.assertContains(response, "Please select at least one evaluation")

        # Works if operation can be applied to at least one
        url_options = (
            f"?evaluation={evaluation1.pk}&evaluation={evaluation2.pk}&target_state={Evaluation.State.PREPARED}"
        )
        response = self.app.get(self.url + url_options, user=self.manager)
        self.assertNotContains(response, "Please select at least one evaluation")

    def test_operation_prepare_sends_email_with_editors_in_cc(self):
        editor_a = baker.make(UserProfile, email="editor-a@example.com")
        editor_b = baker.make(UserProfile, email="editor-b@example.com")
        evaluation = baker.make(Evaluation, state=Evaluation.State.NEW, course=self.course)
        baker.make(Contribution, evaluation=evaluation, contributor=editor_a, role=Contribution.Role.EDITOR)
        baker.make(Contribution, evaluation=evaluation, contributor=editor_b, role=Contribution.Role.EDITOR)
        url_options = f"?evaluation={evaluation.pk}&target_state={Evaluation.State.PREPARED}"
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 1)
        self.assertEqual(actual_emails[0]["additional_cc_users"], {editor_a, editor_b})

    def test_operation_prepare_does_not_put_responsible_into_cc(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.NEW, course=self.course)
        baker.make(Contribution, evaluation=evaluation, contributor=self.responsible, role=Contribution.Role.EDITOR)
        url_options = f"?evaluation={evaluation.pk}&target_state={Evaluation.State.PREPARED}"
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 1)
        self.assertEqual(actual_emails[0]["additional_cc_users"], set())

    def test_operation_prepare_does_not_send_email_to_contributors(self):
        contributor = baker.make(UserProfile, email="contributor@example.com")
        evaluation = baker.make(Evaluation, state=Evaluation.State.NEW, course=self.course)
        baker.make(Contribution, evaluation=evaluation, contributor=contributor, role=Contribution.Role.CONTRIBUTOR)
        url_options = f"?evaluation={evaluation.pk}&target_state={Evaluation.State.PREPARED}"
        actual_emails = self.submit_operation_prepare_form(url_options)

        self.assertEqual(len(actual_emails), 1)
        self.assertEqual(actual_emails[0]["additional_cc_users"], set())

    def test_invalid_target_states(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.APPROVED, course=self.course)
        base_url = f"{self.url}?evaluation={evaluation.pk}"

        self.app.get(f"{base_url}&target_state=133742", user=self.manager, status=400)
        self.app.get(f"{base_url}&target_state=asdf", user=self.manager, status=400)
        self.app.get(f"{base_url}&target_state=", user=self.manager, status=400)
        self.app.get(f"{base_url}&target_state={Evaluation.State.IN_EVALUATION}", user=self.manager, status=200)

    def test_semester_mismatch(self) -> None:
        cases = [
            (self.course, 200),
            (baker.make(Course), 400),
        ]

        for course, status in cases:
            evaluation = baker.make(Evaluation, state=Evaluation.State.NEW, course=course)
            self.app.get(
                f"{self.url}?evaluation={evaluation.pk}&target_state={Evaluation.State.PREPARED}",
                user=self.manager,
                status=status,
            )


class TestCourseCreateView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.course_type = baker.make(CourseType)
        cls.degree = baker.make(Degree)
        cls.responsible = baker.make(UserProfile)
        cls.url = reverse("staff:course_create", args=[cls.semester.pk])

    def prepare_form(self, name_en, name_de):
        response = self.app.get(self.url, user=self.manager, status=200)
        form = response.forms["course-form"]
        form["semester"] = self.semester.pk
        form["type"] = self.course_type.pk
        form["degrees"] = [self.degree.pk]
        form["is_private"] = False
        form["responsibles"] = [self.responsible.pk]
        form["name_en"] = name_en
        form["name_de"] = name_de
        return form

    def test_course_create(self):
        """
        Tests the course creation view with one valid and one invalid input dataset.
        """
        # empty name_en to get a validation error
        form = self.prepare_form(name_en="", name_de="dskr4jre35m6")

        response = form.submit("operation", value="save")
        self.assertIn("This field is required", response)
        self.assertFalse(Course.objects.exists())

        form["name_en"] = "asdf"  # now do it right

        form.submit("operation", value="save")
        self.assertEqual(Course.objects.get().name_de, "dskr4jre35m6")

    @patch("evap.staff.views.redirect")
    def test_operation_redirects(self, mock_redirect):
        mock_redirect.side_effect = lambda *_args: HttpResponse()

        self.prepare_form("a", "b").submit("operation", value="save")
        self.assertEqual(mock_redirect.call_args.args[0], "staff:semester_view")

        self.prepare_form("c", "d").submit("operation", value="save_create_evaluation")
        self.assertEqual(mock_redirect.call_args.args[0], "staff:evaluation_create_for_course")

        self.prepare_form("e", "f").submit("operation", value="save_create_single_result")
        self.assertEqual(mock_redirect.call_args.args[0], "staff:single_result_create_for_course")

        self.assertEqual(mock_redirect.call_count, 3)


class TestSingleResultCreateView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.course = baker.make(Course)
        cls.url_for_semester = reverse("staff:single_result_create_for_semester", args=[cls.course.semester.pk])
        cls.url_for_course = reverse("staff:single_result_create_for_course", args=[cls.course.pk])

    def test_urls_use_common_impl(self):
        for url in [self.url_for_course, self.url_for_semester]:
            with patch("evap.staff.views.single_result_create_impl") as mock:
                mock.return_value = HttpResponse()
                self.app.get(url, user=self.manager)
                mock.assert_called_once()

    def test_course_is_prefilled(self):
        response = self.app.get(self.url_for_course, user=self.manager, status=200)
        form = response.context["form"]
        self.assertEqual(form["course"].initial, self.course.pk)

    def test_single_result_create(self):
        """
        Tests the single result creation view with one valid and one invalid input dataset.
        """
        response = self.app.get(self.url_for_semester, user=self.manager, status=200)
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


class TestEvaluationCreateView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.course = baker.make(Course)
        cls.q1 = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        cls.q2 = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        cls.url_for_semester = reverse("staff:evaluation_create_for_semester", args=[cls.course.semester.pk])
        cls.url_for_course = reverse("staff:evaluation_create_for_course", args=[cls.course.pk])

    def test_urls_use_common_impl(self):
        for url in [self.url_for_course, self.url_for_semester]:
            with patch("evap.staff.views.evaluation_create_impl") as mock:
                mock.return_value = HttpResponse()
                self.app.get(url, user=self.manager)
                mock.assert_called_once()

    def test_course_is_prefilled(self):
        response = self.app.get(self.url_for_course, user=self.manager, status=200)
        form = response.context["evaluation_form"]
        self.assertEqual(form["course"].initial, self.course.pk)

    def test_evaluation_create(self):
        """
        Tests the evaluation creation view with one valid and one invalid input dataset.
        """
        response = self.app.get(self.url_for_semester, user=self.manager, status=200)
        form = response.forms["evaluation-form"]
        form["course"] = self.course.pk
        form["name_de"] = "lfo9e7bmxp1xi"
        form["name_en"] = "asdf"
        form["vote_start_datetime"] = "2099-01-01 00:00:00"
        form["vote_end_date"] = "2014-01-01"  # wrong order to get the validation error
        form["general_questionnaires"] = [self.q1.pk]
        form["wait_for_grade_upload_before_publishing"] = True

        form["contributions-TOTAL_FORMS"] = 1
        form["contributions-INITIAL_FORMS"] = 0
        form["contributions-MAX_NUM_FORMS"] = 5
        form["contributions-0-evaluation"] = ""
        form["contributions-0-contributor"] = self.manager.pk
        form["contributions-0-questionnaires"] = [self.q2.pk]
        form["contributions-0-order"] = 0
        form["contributions-0-role"] = Contribution.Role.EDITOR
        form["contributions-0-textanswer_visibility"] = Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS

        form.submit()
        self.assertFalse(Evaluation.objects.exists())

        form["vote_start_datetime"] = "2014-01-01 00:00:00"
        form["vote_end_date"] = "2099-01-01"  # now do it right

        form.submit()
        self.assertEqual(Evaluation.objects.get().name_de, "lfo9e7bmxp1xi")


class TestEvaluationCopyView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.course = baker.make(Course, semester=cls.semester)
        cls.evaluation = baker.make(
            Evaluation,
            course=cls.course,
            name_de="Das Original",
            name_en="The Original",
        )
        cls.general_questionnaires = baker.make(Questionnaire, _bulk_create=True, _quantity=5)
        cls.evaluation.general_contribution.questionnaires.set(cls.general_questionnaires)
        baker.make(
            Contribution, evaluation=cls.evaluation, _fill_optional=["contributor"], _quantity=3, _bulk_create=True
        )
        cls.url = reverse("staff:evaluation_copy", args=[cls.evaluation.pk])

    def test_copy_forms_are_used(self):
        response = self.app.get(self.url, user=self.manager, status=200)
        self.assertIsInstance(response.context["evaluation_form"], EvaluationCopyForm)
        self.assertIsInstance(response.context["formset"], ContributionCopyFormset)
        self.assertTrue(issubclass(response.context["formset"].form, ContributionCopyForm))

    def test_evaluation_copy(self):
        response = self.app.get(self.url, user=self.manager, status=200)
        form = response.forms["evaluation-form"]
        form["name_de"] = "Eine Kopie"
        form["name_en"] = "A Copy"
        form.submit()

        # As we checked previously that the respective copy forms were used,
        # we don’t have to check for individual attributes, as those are checked in the respective form tests
        self.assertEqual(Evaluation.objects.count(), 2)
        copied_evaluation = Evaluation.objects.exclude(pk=self.evaluation.pk).get()
        self.assertEqual(copied_evaluation.contributions.count(), 4)


class TestCourseCopyView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.other_semester = baker.make(Semester)
        degree = baker.make(Degree)
        cls.responsibles = [
            baker.make(UserProfile, last_name="Muller"),
            baker.make(UserProfile, is_active=False, last_name="Wolf"),
        ]
        cls.course = baker.make(
            Course,
            name_en="Some name",
            semester=cls.semester,
            degrees=[degree],
            responsibles=cls.responsibles,
        )
        cls.evaluation = baker.make(
            Evaluation,
            course=cls.course,
            name_de="Das Original",
            name_en="The Original",
        )
        cls.general_questionnaires = baker.make(Questionnaire, _quantity=5, _bulk_create=True)
        cls.evaluation.general_contribution.questionnaires.set(cls.general_questionnaires)
        baker.make(
            Contribution,
            evaluation=cls.evaluation,
            _quantity=3,
            _bulk_create=True,
            _fill_optional=["contributor"],
        )
        cls.url = reverse("staff:course_copy", args=[cls.course.pk])

    def test_copy_forms_are_used(self):
        response = self.app.get(self.url, user=self.manager, status=200)
        self.assertIsInstance(response.context["course_form"], CourseCopyForm)

    def test_course_copy(self):
        response = self.app.get(self.url, user=self.manager, status=200)
        form = response.forms["course-form"]
        form["semester"] = self.other_semester.pk
        form["vote_start_datetime"] = datetime.datetime(2099, 1, 1, 0, 0)
        form["vote_end_date"] = datetime.date(2099, 12, 31)

        # check that the user activation is mentioned
        self.assertFalse(self.responsibles[1].is_active)
        response = form.submit().follow()
        self.assertIn(self.responsibles[1].full_name, response)

        self.assertEqual(Course.objects.count(), 2)
        copied_course = Course.objects.exclude(pk=self.course.pk).get()
        self.assertEqual(copied_course.evaluations.count(), 1)
        self.assertEqual(set(copied_course.responsibles.all()), set(self.responsibles))

        copied_evaluation = copied_course.evaluations.get()
        self.assertEqual(copied_evaluation.weight, self.evaluation.weight)
        self.assertEqual(
            set(copied_evaluation.general_contribution.questionnaires.all()),
            set(self.evaluation.general_contribution.questionnaires.all()),
        )
        self.assertFalse(copied_course.responsibles.filter(is_active=False).exists())


class TestCourseEditView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.course = baker.make(
            Course,
            name_en="Some name",
            degrees=[baker.make(Degree)],
            responsibles=[baker.make(UserProfile)],
        )
        cls.url = reverse("staff:course_edit", args=[cls.course.pk])

    def prepare_form(self, name_en):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["course-form"]
        form["name_en"] = name_en
        return form

    def test_edit_course(self):
        self.prepare_form(name_en="A different name").submit("operation", value="save")
        self.course = Course.objects.get(pk=self.course.pk)
        self.assertEqual(self.course.name_en, "A different name")

    @patch("evap.staff.views.reverse")
    def test_operation_redirects(self, mock_reverse):
        mock_reverse.return_value = "/very_legit_url"

        response = self.prepare_form("a").submit("operation", value="save")
        self.assertEqual(mock_reverse.call_args.args[0], "staff:semester_view")
        self.assertRedirects(response, "/very_legit_url", fetch_redirect_response=False)

        response = self.prepare_form("b").submit("operation", value="save_create_evaluation")
        self.assertEqual(mock_reverse.call_args.args[0], "staff:evaluation_create_for_course")
        self.assertRedirects(response, "/very_legit_url", fetch_redirect_response=False)

        response = self.prepare_form("c").submit("operation", value="save_create_single_result")
        self.assertEqual(mock_reverse.call_args.args[0], "staff:single_result_create_for_course")
        self.assertRedirects(response, "/very_legit_url", fetch_redirect_response=False)

        self.assertEqual(mock_reverse.call_count, 3)

    @patch("evap.evaluation.models.Course.can_be_edited_by_manager", False)
    def test_uneditable_course(self):
        self.prepare_form(name_en="A different name").submit("operation", value="save", status=400)


class TestCourseDeleteView(DeleteViewTestMixin, WebTestStaffMode):
    url = reverse("staff:course_delete")
    model_cls = Course
    permission_method_to_patch = (Course, "can_be_deleted_by_manager")

    @classmethod
    def get_post_params(cls):
        return {"course_id": cls.instance.pk}


@override_settings(
    REWARD_POINTS=[
        (1 / 3, 1),
        (2 / 3, 2),
        (3 / 3, 3),
    ]
)
class TestEvaluationEditView(WebTestStaffMode):
    render_pages_url = "/staff/semester/PK/evaluation/PK/edit"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        responsible = baker.make(UserProfile)
        cls.editor = baker.make(UserProfile)
        cls.evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, degrees=[baker.make(Degree)], responsibles=[responsible]),
            vote_start_datetime=datetime.datetime(2099, 1, 1, 0, 0),
            vote_end_date=datetime.date(2099, 12, 31),
        )
        cls.url = reverse("staff:evaluation_edit", args=[cls.evaluation.pk])

        baker.make(Questionnaire, questions=[baker.make(Question)])
        cls.general_question = baker.make(Question)
        cls.general_questionnaire = baker.make(Questionnaire, questions=[cls.general_question])
        cls.evaluation.general_contribution.questionnaires.set([cls.general_questionnaire])
        cls.contributor_question = baker.make(Question)
        cls.contributor_questionnaire = baker.make(
            Questionnaire,
            type=Questionnaire.Type.CONTRIBUTOR,
            questions=[cls.contributor_question],
        )
        cls.contribution1 = baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=responsible,
            order=0,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        cls.contribution2 = baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=cls.editor,
            order=1,
            role=Contribution.Role.EDITOR,
        )
        cls.contribution1.questionnaires.set([cls.contributor_questionnaire])
        cls.contribution2.questionnaires.set([cls.contributor_questionnaire])

    @render_pages
    def render_pages(self):
        return {
            "normal": self.app.get(self.url, user=self.manager).content,
        }

    def test_edit_evaluation(self):
        page = self.app.get(self.url, user=self.manager)

        # remove editor rights
        form = page.forms["evaluation-form"]
        form["contributions-1-role"] = Contribution.Role.CONTRIBUTOR
        form.submit("operation", value="save")
        self.assertEqual(self.evaluation.contributions.get(contributor=self.editor).role, Contribution.Role.CONTRIBUTOR)

    def test_participant_removal_reward_point_granting_message(self):
        already_evaluated = baker.make(Evaluation, course__semester=self.evaluation.course.semester)
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        other = baker.make(UserProfile, evaluations_participating_in=[self.evaluation])
        student = baker.make(
            UserProfile,
            email="foo@institution.example.com",
            evaluations_participating_in=[self.evaluation, already_evaluated],
            evaluations_voted_for=[already_evaluated],
        )

        page = self.app.get(self.url, user=self.manager)

        # remove a single participant
        form = page.forms["evaluation-form"]
        form["participants"] = [other.pk]
        page = form.submit("operation", value="save").follow()

        self.assertIn(
            f"The removal as participant has granted the user &quot;{student.email}&quot; "
            "3 reward points for the semester.",
            page,
        )

    def test_remove_participants(self):
        already_evaluated = baker.make(Evaluation, course__semester=self.evaluation.course.semester)
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        student = baker.make(UserProfile, evaluations_participating_in=[self.evaluation])

        baker.make(
            UserProfile,
            email=iter(f"{name}@institution.example.com" for name in ["a", "b", "c", "d", "e"]),
            evaluations_participating_in=[self.evaluation, already_evaluated],
            evaluations_voted_for=[already_evaluated],
            _quantity=5,
        )

        page = self.app.get(self.url, user=self.manager)

        # remove five participants
        form = page.forms["evaluation-form"]
        form["participants"] = [student.pk]
        page = form.submit("operation", value="save").follow()

        for name in ["a", "b", "c", "d", "e"]:
            self.assertIn(
                f"The removal as participant has granted the user &quot;{name}@institution.example.com&quot; 3 reward points for the semester.",
                page,
            )

    def test_remove_participants_proportional_reward_points(self):
        already_evaluated = baker.make(Evaluation, course__semester=self.evaluation.course.semester)
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        student = baker.make(UserProfile, evaluations_participating_in=[self.evaluation])

        users = baker.make(
            UserProfile,
            email=iter(f"{name}@institution.example.com" for name in ["a", "b", "c", "d"]),
            evaluations_participating_in=[self.evaluation, already_evaluated],
            evaluations_voted_for=[already_evaluated],
            _quantity=4,
        )
        baker.make(
            RewardPointGranting,
            user_profile=iter(users),
            semester=self.evaluation.course.semester,
            value=iter([0, 1, 2, 3]),
            _quantity=4,
            _bulk_create=True,
        )

        page = self.app.get(self.url, user=self.manager)

        # remove four participants
        form = page.forms["evaluation-form"]
        form["participants"] = [student.pk]
        page = form.submit("operation", value="save").follow()

        self.assertIn(
            "The removal as participant has granted the user &quot;a@institution.example.com&quot; 3 reward points for the semester.",
            page,
        )
        self.assertIn(
            "The removal as participant has granted the user &quot;b@institution.example.com&quot; 2 reward points for the semester.",
            page,
        )
        self.assertIn(
            "The removal as participant has granted the user &quot;c@institution.example.com&quot; 1 reward point for the semester.",
            page,
        )
        self.assertNotIn("The removal as participant has granted the user &quot;d@institution.example.com&quot;", page)

    def test_questionnaire_with_answers_warning(self):
        page = self.app.get(self.url, user=self.manager)
        self.assertIn('<label class="form-check-label" for="id_general_questionnaires_3">', page)
        self.assertIn('<label class="form-check-label" for="id_contributions-0-questionnaires_0">', page)
        self.assertIn('<label class="form-check-label" for="id_contributions-1-questionnaires_0">', page)

        baker.make(TextAnswer, contribution=self.evaluation.general_contribution, question=self.general_question)
        baker.make(RatingAnswerCounter, contribution=self.contribution1, question=self.contributor_question)

        page = self.app.get(self.url, user=self.manager)
        self.assertIn('<label class="form-check-label badge bg-danger" for="id_general_questionnaires_3">', page)
        self.assertIn(
            '<label class="form-check-label badge bg-danger" for="id_contributions-0-questionnaires_0">', page
        )
        self.assertNotIn(
            '<label class="form-check-label badge bg-danger" for="id_contributions-1-questionnaires_0">', page
        )

        baker.make(RatingAnswerCounter, contribution=self.contribution2, question=self.contributor_question)

        page = self.app.get(self.url, user=self.manager)
        self.assertIn(
            '<label class="form-check-label badge bg-danger" for="id_contributions-1-questionnaires_0">', page
        )

    @patch.dict(Evaluation.STATE_STR_CONVERSION, {Evaluation.State.PREPARED: "mock-translated-prepared"})
    def test_state_change_log_translated(self):
        page = self.app.get(self.url, user=self.manager)
        self.assertNotIn("mock-translated-prepared", page)

        self.evaluation.ready_for_editors()
        self.evaluation.save()

        page = self.app.get(self.url, user=self.manager)
        self.assertIn("mock-translated-prepared", page)


class TestEvaluationDeleteView(WebTestStaffMode):
    csrf_checks = False
    url = reverse("staff:evaluation_delete")

    @classmethod
    def setUpTestData(cls):
        cls.evaluation = baker.make(Evaluation)
        cls.manager = make_manager()
        cls.post_params = {"evaluation_id": cls.evaluation.pk}

    @patch.object(Evaluation, "can_be_deleted_by_manager", True)
    @patch("evap.staff.views.update_template_cache_of_published_evaluations_in_course")
    def test_valid_deletion(self, update_template_cache_mock):
        self.app.post(self.url, user=self.manager, params=self.post_params)

        update_template_cache_mock.assert_called_once_with(self.evaluation.course)
        self.assertFalse(Evaluation.objects.filter(pk=self.evaluation.pk).exists())

    @patch.object(Evaluation, "can_be_deleted_by_manager", True)
    def test_single_result_deletion(self):
        self.evaluation.is_single_result = True
        self.evaluation.save()
        counters = baker.make(
            RatingAnswerCounter, contribution__evaluation=self.evaluation, _quantity=5, _bulk_create=True
        )

        self.app.post(self.url, user=self.manager, params=self.post_params, status=200)

        self.assertFalse(Evaluation.objects.filter(pk=self.evaluation.pk).exists())
        self.assertFalse(RatingAnswerCounter.objects.filter(pk__in=[c.pk for c in counters]).exists())

    @patch.object(Evaluation, "can_be_deleted_by_manager", False)
    def test_invalid_deletion(self):
        self.app.post(self.url, user=self.manager, params=self.post_params, status=400)
        self.assertTrue(Evaluation.objects.filter(pk=self.evaluation.pk).exists())


class TestSingleResultEditView(WebTestStaffModeWith200Check):
    @classmethod
    def setUpTestData(cls):
        result = create_evaluation_with_responsible_and_editor()
        evaluation = result["evaluation"]
        contribution = result["contribution"]

        cls.test_users = [make_manager()]
        cls.url = reverse("staff:evaluation_edit", args=[evaluation.pk])

        evaluation.is_single_result = True
        evaluation.save()

        contribution.textanswer_visibility = Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS
        contribution.questionnaires.set([Questionnaire.single_result_questionnaire()])
        contribution.save()

        question = Questionnaire.single_result_questionnaire().questions.get()
        make_rating_answer_counters(question, contribution, [5, 15, 40, 60, 30])


class TestEvaluationPreviewView(WebTestStaffModeWith200Check):
    @classmethod
    def setUpTestData(cls):
        cls.evaluation = baker.make(Evaluation)
        cls.evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        cls.manager = make_manager()
        cls.test_users = [cls.manager]
        cls.url = reverse("staff:evaluation_preview", args=[cls.evaluation.pk])

    def test_without_questionnaires_assigned(self):
        # regression test for #1747
        self.evaluation.general_contribution.questionnaires.set([])
        self.app.get(self.url, user=self.manager, status=200)


class TestEvaluationImportPersonsView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.valid_excel_file_content = excel_data.create_memory_excel_file(excel_data.valid_user_import_filedata)
        cls.missing_values_excel_file_content = excel_data.create_memory_excel_file(
            excel_data.missing_values_user_import_filedata
        )
        cls.random_excel_file_content = excel_data.random_file_content

        semester = baker.make(Semester)

        cls.manager = make_manager()
        profiles1 = baker.make(UserProfile, _bulk_create=True, _quantity=31)
        cls.evaluation = baker.make(Evaluation, course__semester=semester, participants=profiles1)

        profiles2 = baker.make(UserProfile, _bulk_create=True, _quantity=42)
        cls.evaluation2 = baker.make(Evaluation, course__semester=semester, participants=profiles2)
        cls.contribution2 = baker.make(Contribution, evaluation=cls.evaluation2, _fill_optional=["contributor"])

        cls.url = reverse("staff:evaluation_person_management", args=[cls.evaluation.pk])
        cls.url2 = reverse("staff:evaluation_person_management", args=[cls.evaluation2.pk])

    def tearDown(self):
        # delete the uploaded file again so other tests can start with no file guaranteed
        helper_delete_all_import_files(self.manager.id)

    def test_import_valid_participants_file(self):
        page = self.app.get(self.url, user=self.manager)

        original_participant_count = self.evaluation.participants.count()

        form = page.forms["participant-import-form"]
        form["pe-excel_file"] = ("import.xls", self.valid_excel_file_content)
        page = form.submit(name="operation", value="test-participants")

        self.assertContains(page, "Import previously uploaded file")
        self.assertEqual(self.evaluation.participants.count(), original_participant_count)

        form = page.forms["participant-import-form"]
        submit_with_modal(page, form, name="operation", value="import-participants")
        self.assertEqual(self.evaluation.participants.count(), original_participant_count + 2)

        page = self.app.get(self.url, user=self.manager)
        self.assertNotContains(page, "Import previously uploaded file")

    def test_replace_valid_participants_file(self):
        page = self.app.get(self.url2, user=self.manager)

        form = page.forms["participant-import-form"]
        form["pe-excel_file"] = ("import.xls", self.valid_excel_file_content)
        page = form.submit(name="operation", value="test-participants")

        self.assertNotEqual(self.evaluation2.participants.count(), 2)

        form = page.forms["participant-import-form"]
        submit_with_modal(page, form, name="operation", value="import-replace-participants")
        self.assertEqual(self.evaluation2.participants.count(), 2)

        page = self.app.get(self.url2, user=self.manager)
        self.assertNotContains(page, "Import previously uploaded file")

    def test_copy_participants(self):
        page = self.app.get(self.url, user=self.manager)

        original_participant_count = self.evaluation.participants.count()

        form = page.forms["participant-copy-form"]
        form["pc-evaluation"] = str(self.evaluation2.pk)
        page = submit_with_modal(page, form, name="operation", value="copy-participants")

        self.assertEqual(
            self.evaluation.participants.count(), original_participant_count + self.evaluation2.participants.count()
        )

    def test_copy_invalid_participants(self):
        page = self.app.get(self.url, user=self.manager)

        old_evaluation = baker.make(
            Evaluation,
            course__semester=self.evaluation2.course.semester,
            participants=self.evaluation2.participants.all(),
        )
        old_pk = old_evaluation.pk
        old_evaluation.delete()

        form = page.forms["participant-copy-form"]
        form["pc-evaluation"] = str(self.evaluation2.pk)
        params = dict(form.submit_fields() + [("operation", "copy-replace-participants")])
        params["pc-evaluation"] = str(old_pk)
        form.response.goto(form.action, method=form.method, params=params, status=400)

    def test_replace_copy_participants(self):
        page = self.app.get(self.url, user=self.manager)

        self.assertNotEqual(self.evaluation.participants.count(), self.evaluation2.participants.count())

        form = page.forms["participant-copy-form"]
        form["pc-evaluation"] = str(self.evaluation2.pk)
        page = submit_with_modal(page, form, name="operation", value="copy-replace-participants")

        self.assertEqual(self.evaluation.participants.count(), self.evaluation2.participants.count())

    def test_import_valid_contributors_file(self):
        page = self.app.get(self.url, user=self.manager)

        original_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()

        form = page.forms["contributor-import-form"]
        form["ce-excel_file"] = ("import.xls", self.valid_excel_file_content)
        page = form.submit(name="operation", value="test-contributors")

        self.assertContains(page, "Import previously uploaded file")
        self.assertEqual(
            UserProfile.objects.filter(contributions__evaluation=self.evaluation).count(), original_contributor_count
        )

        form = page.forms["contributor-import-form"]
        submit_with_modal(page, form, name="operation", value="import-contributors")
        self.assertEqual(
            UserProfile.objects.filter(contributions__evaluation=self.evaluation).count(),
            original_contributor_count + 2,
        )

        page = self.app.get(self.url, user=self.manager)
        self.assertNotContains(page, "Import previously uploaded file")

    def test_replace_valid_contributors_file(self):
        page = self.app.get(self.url2, user=self.manager)

        form = page.forms["contributor-import-form"]
        form["ce-excel_file"] = ("import.xls", self.valid_excel_file_content)
        page = form.submit(name="operation", value="test-contributors")

        self.assertNotEqual(UserProfile.objects.filter(contributions__evaluation=self.evaluation2).count(), 2)

        form = page.forms["contributor-import-form"]
        submit_with_modal(page, form, name="operation", value="import-replace-contributors")
        self.assertEqual(UserProfile.objects.filter(contributions__evaluation=self.evaluation2).count(), 2)

        page = self.app.get(self.url, user=self.manager)
        self.assertNotContains(page, "Import previously uploaded file")

    def test_copy_contributors(self):
        page = self.app.get(self.url, user=self.manager)

        original_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()

        form = page.forms["contributor-copy-form"]
        form["cc-evaluation"] = str(self.evaluation2.pk)
        page = submit_with_modal(page, form, name="operation", value="copy-contributors")

        new_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()
        self.assertEqual(
            new_contributor_count,
            original_contributor_count + UserProfile.objects.filter(contributions__evaluation=self.evaluation2).count(),
        )

    def test_copy_replace_contributors(self):
        page = self.app.get(self.url, user=self.manager)

        old_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()
        self.assertNotEqual(
            old_contributor_count, UserProfile.objects.filter(contributions__evaluation=self.evaluation2).count()
        )

        form = page.forms["contributor-copy-form"]
        form["cc-evaluation"] = str(self.evaluation2.pk)
        page = submit_with_modal(page, form, name="operation", value="copy-replace-contributors")

        new_contributor_count = UserProfile.objects.filter(contributions__evaluation=self.evaluation).count()
        self.assertEqual(
            new_contributor_count, UserProfile.objects.filter(contributions__evaluation=self.evaluation2).count()
        )

    def test_import_participants_error_handling(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        form["pe-excel_file"] = ("import.xls", self.missing_values_excel_file_content)

        reply = form.submit(name="operation", value="test-participants")

        self.assertContains(
            reply,
            "Sheet &quot;Sheet 1&quot;, row 2: User missing.firstname@institution.example.com: First name is missing.",
        )
        self.assertContains(
            reply,
            "Sheet &quot;Sheet 1&quot;, row 3: User missing.lastname@institution.example.com: Last name is missing.",
        )
        self.assertContains(reply, "Sheet &quot;Sheet 1&quot;, row 4: Email address is missing.")
        self.assertContains(reply, "Errors occurred while parsing the input data. No data was imported.")
        self.assertNotContains(reply, "Import previously uploaded file")

    def test_import_participants_warning_handling(self):
        user = baker.make(UserProfile, email="lucilia.manilium@institution.example.com")

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        form["pe-excel_file"] = ("import.xls", self.valid_excel_file_content)

        reply = form.submit(name="operation", value="test-participants")
        self.assertContains(
            reply,
            "The existing user would be overwritten with the following data:<br />"
            f" -  (empty) (empty), lucilia.manilium@institution.example.com [{user_edit_link(user.pk)}] (existing)<br />"
            " -  Lucilia Manilium, lucilia.manilium@institution.example.com (import)",
        )
        self.assertContains(reply, "Import previously uploaded file")
        helper_delete_all_import_files(self.manager.id)

    def test_import_contributors_error_handling(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["contributor-import-form"]
        form["ce-excel_file"] = ("import.xls", self.missing_values_excel_file_content)

        reply = form.submit(name="operation", value="test-contributors")

        self.assertContains(
            reply,
            "Sheet &quot;Sheet 1&quot;, row 2: User missing.firstname@institution.example.com: First name is missing.",
        )
        self.assertContains(
            reply,
            "Sheet &quot;Sheet 1&quot;, row 3: User missing.lastname@institution.example.com: Last name is missing.",
        )
        self.assertContains(reply, "Sheet &quot;Sheet 1&quot;, row 4: Email address is missing.")
        self.assertContains(reply, "Errors occurred while parsing the input data. No data was imported.")
        self.assertNotContains(reply, "Import previously uploaded file")

    def test_import_contributors_warning_handling(self):
        user = baker.make(UserProfile, email="lucilia.manilium@institution.example.com")

        page = self.app.get(self.url, user=self.manager)

        form = page.forms["contributor-import-form"]
        form["ce-excel_file"] = ("import.xls", self.valid_excel_file_content)

        reply = form.submit(name="operation", value="test-contributors")
        self.assertContains(reply, "Name mismatches")
        self.assertContains(
            reply,
            "The existing user would be overwritten with the following data:<br />"
            f" -  (empty) (empty), lucilia.manilium@institution.example.com [{user_edit_link(user.pk)}] (existing)<br />"
            " -  Lucilia Manilium, lucilia.manilium@institution.example.com (import)",
        )
        self.assertContains(reply, "Import previously uploaded file")
        helper_delete_all_import_files(self.manager.id)

    def test_suspicious_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        form["pe-excel_file"] = ("import.xls", self.valid_excel_file_content)

        form.submit(name="operation", value="hackit", status=400)

    def test_invalid_contributor_upload_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["contributor-import-form"]
        page = form.submit(name="operation", value="test-contributors")

        self.assertContains(page, "This field is required.")
        self.assertNotContains(page, "Import previously uploaded file")

    def test_invalid_participant_upload_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        page = form.submit(name="operation", value="test-participants")

        self.assertContains(page, "This field is required.")
        self.assertNotContains(page, "Import previously uploaded file")

    def test_invalid_contributor_import_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["contributor-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        form.submit(name="operation", value="import-contributors", status=400)

    def test_invalid_participant_import_operation(self):
        page = self.app.get(self.url, user=self.manager)

        form = page.forms["participant-import-form"]
        # invalid because no file has been uploaded previously (and the button doesn't even exist)
        form.submit(name="operation", value="import-participants", status=400)


class TestEvaluationEmailView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        participant1 = baker.make(UserProfile, email="foo@example.com")
        participant2 = baker.make(UserProfile, email="bar@example.com")
        evaluation = baker.make(Evaluation, participants=[participant1, participant2])
        cls.url = reverse("staff:evaluation_email", args=[evaluation.pk])

    def test_emails_are_sent(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["evaluation-email-form"]
        form.get("recipients", index=0).checked = True  # send to all participants
        form["subject"] = "asdf"
        form["plain_content"] = "asdf"
        form["html_content"] = "<p>asdf</p>"
        form.submit()

        self.assertEqual(len(mail.outbox), 2)


class TestEvaluationTextAnswerView(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.student1 = baker.make(UserProfile, email="student@institution.example.com")
        cls.student2 = baker.make(UserProfile, email="student2@example.com")

        cls.evaluation = baker.make(
            Evaluation,
            course__semester=cls.semester,
            participants=[cls.student1, cls.student2],
            voters=[cls.student1],
            state=Evaluation.State.IN_EVALUATION,
        )
        cls.url = reverse("staff:evaluation_textanswers", args=[cls.evaluation.pk])
        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=top_general_questionnaire, type=QuestionType.POSITIVE_LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])

        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, questionnaire=questionnaire, type=QuestionType.TEXT)
        contribution = baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=baker.make(UserProfile),
            questionnaires=[questionnaire],
        )
        cls.answer = "should show up"
        baker.make(TextAnswer, contribution=contribution, question=question, answer=cls.answer)
        cls.reviewed_answer = "someone reviewed me already"
        baker.make(
            TextAnswer,
            contribution=contribution,
            question=question,
            answer=cls.reviewed_answer,
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )

        cls.evaluation2 = baker.make(
            Evaluation,
            course__semester=cls.semester,
            participants=[cls.student1],
            voters=[cls.student1, cls.student2],
            vote_start_datetime=datetime.datetime.now() - datetime.timedelta(days=5),
            vote_end_date=datetime.date.today() - datetime.timedelta(days=4),
            can_publish_text_results=True,
        )

        contribution2 = baker.make(
            Contribution,
            evaluation=cls.evaluation2,
            contributor=baker.make(UserProfile),
            questionnaires=[questionnaire],
        )
        cls.text_answer = baker.make(
            TextAnswer,
            contribution=contribution2,
            question=question,
            answer="test answer text",
        )

    def test_textanswers_showing_up(self):
        # in an evaluation with only one voter the view should not be available
        with run_in_staff_mode(self):
            self.app.get(self.url, user=self.manager, status=403)

        # add additional voter
        let_user_vote_for_evaluation(self.student2, self.evaluation)

        # now it should work
        with run_in_staff_mode(self):
            self.app.get(self.url, user=self.manager, status=200)

    def test_textanswers_quick_view(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        with run_in_staff_mode(self):
            page = self.app.get(self.url, user=self.manager, status=200)
            self.assertContains(page, self.answer)
            self.assertContains(page, self.reviewed_answer)

    def test_textanswers_full_view(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        with run_in_staff_mode(self):
            page = self.app.get(self.url + "?view=full", user=self.manager, status=200)
            self.assertContains(page, self.answer)
            self.assertContains(page, self.reviewed_answer)

    def test_textanswers_undecided_view(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        with run_in_staff_mode(self):
            page = self.app.get(self.url + "?view=undecided", user=self.manager, status=200)
            self.assertContains(page, self.answer)
            self.assertNotContains(page, self.reviewed_answer)

    # use offset of more than 25 hours to make sure the test doesn't fail even on combined time zone change and leap second
    @override_settings(EVALUATION_END_OFFSET_HOURS=26)
    def test_exclude_unfinished_evaluations(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        with run_in_staff_mode(self):
            page = self.app.get(self.url, user=self.manager, status=200)
            # evaluation2 is finished and should show up
            self.assertContains(page, self.evaluation2.full_name)

        self.evaluation2.vote_end_date = datetime.date.today() - datetime.timedelta(days=1)
        self.evaluation2.save()
        with run_in_staff_mode(self):
            page = self.app.get(self.url, user=self.manager, status=200)
            # unfinished because still in EVALUATION_END_OFFSET_HOURS
            self.assertNotContains(page, self.evaluation2.full_name)

    def test_exclude_evaluations_with_only_flagged(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        let_user_vote_for_evaluation(self.student2, self.evaluation2, create_answers=True)
        self.assertGreaterEqual(TextAnswer.objects.filter(contribution__evaluation=self.evaluation2).count(), 2)

        with run_in_staff_mode(self):
            page = self.app.get(self.url, user=self.manager)
            self.assertContains(page, self.evaluation2.full_name)

        TextAnswer.objects.filter(contribution__evaluation=self.evaluation2).update(is_flagged=True)
        with run_in_staff_mode(self):
            page = self.app.get(self.url, user=self.manager)
            self.assertNotContains(page, self.evaluation2.full_name)

        t1 = TextAnswer.objects.filter(contribution__evaluation=self.evaluation2).first()
        t1.is_flagged = False
        t1.save()

        with run_in_staff_mode(self):
            page = self.app.get(self.url, user=self.manager)
            self.assertContains(page, self.evaluation2.full_name)

    def test_suggested_evaluation_ordering(self):
        evaluations = baker.make(
            Evaluation,
            course__semester=self.semester,
            participants=[self.student1, self.student2],
            voters=[self.student1, self.student2],
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.datetime.now() - datetime.timedelta(days=42),
            vote_end_date=datetime.date.today() - datetime.timedelta(days=2),
            can_publish_text_results=True,
            _quantity=2,
        )

        for evaluation, answer_count in zip(evaluations, [1, 2], strict=True):
            contribution = baker.make(Contribution, evaluation=evaluation, _fill_optional=["contributor"])
            baker.make(TextAnswer, contribution=contribution, question__type=QuestionType.TEXT, _quantity=answer_count)

        url = reverse("staff:evaluation_textanswers", args=[self.evaluation2.pk])

        with run_in_staff_mode(self):
            # Since Evaluation 1 has an extra text answer, it should be first
            page = self.app.get(url, user=self.manager)
            self.assertIn(
                f'data-evaluation="{evaluations[1].pk}"',
                str(page.html.select_one("span[data-next-evaluation-index]")),
            )

            # Since Evaluation 0 has an earlier end date, it should now be first
            evaluations[0].vote_end_date = datetime.date.today() - datetime.timedelta(days=4)
            evaluations[0].save()
            page = self.app.get(url, user=self.manager)
            self.assertIn(
                f'data-evaluation="{evaluations[0].pk}"',
                str(page.html.select_one("span[data-next-evaluation-index]")),
            )

            # Since the grading process for Evaluation 1 is finished, it should be first
            evaluations[1].wait_for_grade_upload_before_publishing = False
            evaluations[1].save()
            page = self.app.get(url, user=self.manager)
            self.assertIn(
                f'data-evaluation="{evaluations[1].pk}"',
                str(page.html.select_one("span[data-next-evaluation-index]")),
            )

    def test_num_queries_is_constant(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)

        kwargs = {"_quantity": 100, "_bulk_create": True}
        contributors = baker.make(UserProfile, **kwargs)
        contributions = baker.make(Contribution, evaluation=self.evaluation, contributor=iter(contributors), **kwargs)
        questionnaires = baker.make(Questionnaire, **kwargs)
        questions = baker.make(
            Question,
            questionnaire=iter(questionnaires),
            type=QuestionType.TEXT,
            allows_additional_textanswers=False,
            **kwargs,
        )
        baker.make(TextAnswer, question=iter(questions), contribution=iter(contributions), **kwargs)

        with run_in_staff_mode(self):
            with self.assertNumQueries(FuzzyInt(0, 100)):
                self.app.get(self.url, user=self.manager)

    def test_published(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        with run_in_staff_mode(self):
            self.app.get(self.url, user=self.manager, status=200)
        Evaluation.objects.filter(id=self.evaluation.id).update(state=Evaluation.State.PUBLISHED)
        with run_in_staff_mode(self):
            self.app.get(self.url, user=self.manager, status=403)

    def test_archived(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        with run_in_staff_mode(self):
            self.app.get(self.url, user=self.manager, status=200)
        Semester.objects.filter(id=self.evaluation.course.semester.id).update(results_are_archived=True)
        with run_in_staff_mode(self):
            self.app.get(self.url, user=self.manager, status=403)


class TestEvaluationTextAnswerEditView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        student1 = baker.make(UserProfile, email="student1@institution.example.com")
        cls.student2 = baker.make(UserProfile, email="student2@example.com")

        cls.evaluation = baker.make(
            Evaluation,
            participants=[student1, cls.student2],
            voters=[student1],
            state=Evaluation.State.IN_EVALUATION,
        )
        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=top_general_questionnaire, type=QuestionType.POSITIVE_LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])
        question = baker.make(Question, type=QuestionType.TEXT)

        contribution = baker.make(
            Contribution,
            evaluation=cls.evaluation,
            questionnaires=[question.questionnaire],
            _fill_optional=["contributor"],
        )
        cls.textanswer = baker.make(
            TextAnswer,
            contribution=contribution,
            question=question,
            answer="test answer text",
        )

        cls.url = reverse(
            "staff:evaluation_textanswer_edit",
            args=[cls.textanswer.pk],
        )

    def test_textanswers_showing_up(self):
        # in an evaluation with only one voter the view should not be available
        self.app.get(self.url, user=self.manager, status=403)

        # add additional voter
        let_user_vote_for_evaluation(self.student2, self.evaluation)

        # now it should work
        response = self.app.get(self.url, user=self.manager)

        form = response.forms["textanswer-edit-form"]
        self.assertEqual(form["answer"].value, "test answer text")
        form["answer"] = "edited answer text"
        form.submit()

        self.textanswer.refresh_from_db()
        self.assertEqual(self.textanswer.answer, "edited answer text")

        # archive and it shouldn't work anymore
        self.app.get(self.url, user=self.manager, status=200)
        Semester.objects.filter(id=self.evaluation.course.semester.id).update(results_are_archived=True)
        self.app.get(self.url, user=self.manager, status=403)
        Semester.objects.filter(id=self.evaluation.course.semester.id).update(results_are_archived=False)

        # publish and it shouldn't work anymore
        self.app.get(self.url, user=self.manager, status=200)
        Evaluation.objects.filter(id=self.evaluation.id).update(state=Evaluation.State.PUBLISHED)
        self.app.get(self.url, user=self.manager, status=403)


class TestSemesterFlaggedTextAnswersView(WebTestStaffMode):
    def test_correct_answers_show_up(self):
        semester = baker.make(Semester)

        url = reverse("staff:semester_flagged_textanswers", args=[semester.pk])

        manager = make_manager()
        student = baker.make(UserProfile)
        evaluations = baker.make(Evaluation, course__semester=semester, participants=[student], _quantity=3)
        textanswers = [
            [baker.make(TextAnswer, answer=f"Answer {i} {j}", contribution__evaluation=evaluation) for j in range(3)]
            for i, evaluation in enumerate(evaluations)
        ]

        response = self.app.get(url, user=manager)
        self.assertContains(response, "There are no flagged textanswers")

        flagged_ids = [(0, 0), (0, 1), (1, 0)]
        expected_texts = [
            "Answer 0 0",
            "Answer 0 1",
            "Answer 1 0",
            evaluations[0].full_name,
            evaluations[1].full_name,
        ]
        unexpected_texts = [
            "There are no flagged textanswers",
            "Answer 0 2",
            "Answer 1 1",
            "Answer 2 0",
            evaluations[2].full_name,
        ]

        for i, j in flagged_ids:
            textanswers[i][j].is_flagged = True
            textanswers[i][j].save()

        response = self.app.get(url, user=manager)

        for text in expected_texts:
            self.assertContains(response, text)
        for text in unexpected_texts:
            self.assertNotContains(response, text)


class TestQuestionnaireNewVersionView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.name_de_orig = "kurzer name"
        cls.name_en_orig = "short name"
        questionnaire = baker.make(Questionnaire, name_de=cls.name_de_orig, name_en=cls.name_en_orig)
        cls.url = f"/staff/questionnaire/{questionnaire.pk}/new_version"

        baker.make(Question, questionnaire=questionnaire)

    def test_changes_old_title(self):
        page = self.app.get(url=self.url, user=self.manager)
        form = page.forms["questionnaire-form"]

        form.submit()

        timestamp = datetime.date.today()
        new_name_de = f"{self.name_de_orig} (until {timestamp})"
        new_name_en = f"{self.name_en_orig} (until {timestamp})"

        self.assertTrue(Questionnaire.objects.filter(name_de=self.name_de_orig, name_en=self.name_en_orig).exists())
        self.assertTrue(Questionnaire.objects.filter(name_de=new_name_de, name_en=new_name_en).exists())

    def test_no_second_update(self):
        # First save.
        page = self.app.get(url=self.url, user=self.manager)
        form = page.forms["questionnaire-form"]
        form.submit()

        # Second try.
        new_questionnaire = Questionnaire.objects.get(name_de=self.name_de_orig)
        page = self.app.get(
            url=f"/staff/questionnaire/{new_questionnaire.id}/new_version", user=self.manager, status=302
        )

        # We should get redirected back to the questionnaire index.
        self.assertEqual(page.location, "/staff/questionnaire/")


class TestQuestionnaireCreateView(WebTestStaffMode):
    url = "/staff/questionnaire/create"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_create_questionnaire(self):
        page = self.app.get(self.url, user=self.manager)

        questionnaire_form = page.forms["questionnaire-form"]
        questionnaire_form["name_de"] = "Test Fragebogen"
        questionnaire_form["name_en"] = "test questionnaire"
        questionnaire_form["public_name_de"] = "Oeffentlicher Test Fragebogen"
        questionnaire_form["public_name_en"] = "Public Test Questionnaire"
        questionnaire_form["questions-0-text_de"] = "Frage 1"
        questionnaire_form["questions-0-text_en"] = "Question 1"
        questionnaire_form["questions-0-type"] = QuestionType.TEXT
        questionnaire_form["order"] = 0
        questionnaire_form["type"] = Questionnaire.Type.TOP
        questionnaire_form.submit().follow()

        # retrieve new questionnaire
        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
        self.assertEqual(questionnaire.questions.count(), 1)

    def test_create_empty_questionnaire(self):
        page = self.app.get(self.url, user=self.manager)

        questionnaire_form = page.forms["questionnaire-form"]
        questionnaire_form["name_de"] = "Test Fragebogen"
        questionnaire_form["name_en"] = "test questionnaire"
        questionnaire_form["public_name_de"] = "Oeffentlicher Test Fragebogen"
        questionnaire_form["public_name_en"] = "Public Test Questionnaire"
        questionnaire_form["order"] = 0
        page = questionnaire_form.submit()

        self.assertIn("You must have at least one of these", page)

        self.assertFalse(Questionnaire.objects.filter(name_de="Test Fragebogen", name_en="test questionnaire").exists())


class TestQuestionnaireIndexView(WebTestStaffMode):
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


class TestQuestionnaireEditView(WebTestStaffModeWith200Check):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.test_users = [cls.manager]

        evaluation = baker.make(Evaluation, state=Evaluation.State.IN_EVALUATION)
        cls.questionnaire = baker.make(Questionnaire)
        cls.url = f"/staff/questionnaire/{cls.questionnaire.pk}/edit"

        baker.make(Contribution, questionnaires=[cls.questionnaire], evaluation=evaluation)

        baker.make(Question, questionnaire=cls.questionnaire)

    def test_allowed_type_changes_on_used_questionnaire(self):
        # top to bottom
        self.questionnaire.type = Questionnaire.Type.TOP
        self.questionnaire.save()

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["questionnaire-form"]
        self.assertEqual(
            form["type"].options, [("10", True, "Top questionnaire"), ("30", False, "Bottom questionnaire")]
        )

        # bottom to top
        self.questionnaire.type = Questionnaire.Type.BOTTOM
        self.questionnaire.save()

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["questionnaire-form"]
        self.assertEqual(
            form["type"].options, [("10", False, "Top questionnaire"), ("30", True, "Bottom questionnaire")]
        )

        # contributor has no other possible type
        self.questionnaire.type = Questionnaire.Type.CONTRIBUTOR
        self.questionnaire.save()

        page = self.app.get(self.url, user=self.manager)
        form = page.forms["questionnaire-form"]
        self.assertEqual(form["type"].options, [("20", True, "Contributor questionnaire")])


class TestQuestionnaireViewView(WebTestStaffModeWith200Check):
    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]

        questionnaire = baker.make(Questionnaire)
        cls.url = f"/staff/questionnaire/{questionnaire.pk}"

        baker.make(
            Question,
            questionnaire=questionnaire,
            type=iter([QuestionType.TEXT, QuestionType.GRADE, QuestionType.POSITIVE_LIKERT]),
            _quantity=3,
            _bulk_create=True,
            allows_additional_textanswers=False,
        )


class TestQuestionnaireCopyView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        questionnaire = baker.make(Questionnaire)
        cls.url = f"/staff/questionnaire/{questionnaire.pk}/copy"

        baker.make(Question, questionnaire=questionnaire)

    def test_not_changing_name_fails(self):
        response = self.app.get(self.url, user=self.manager, status=200)
        response = response.forms["questionnaire-form"].submit("", status=200)
        self.assertIn("already exists", response)

    def test_copy_questionnaire(self):
        page = self.app.get(self.url, user=self.manager)

        questionnaire_form = page.forms["questionnaire-form"]
        questionnaire_form["name_de"] = "Test Fragebogen (kopiert)"
        questionnaire_form["name_en"] = "test questionnaire (copied)"
        questionnaire_form["public_name_de"] = "Oeffentlicher Test Fragebogen (kopiert)"
        questionnaire_form["public_name_en"] = "Public Test Questionnaire (copied)"
        page = questionnaire_form.submit().follow()

        questionnaire = Questionnaire.objects.get(
            name_de="Test Fragebogen (kopiert)", name_en="test questionnaire (copied)"
        )
        self.assertEqual(questionnaire.questions.count(), 1)


class TestQuestionnaireDeleteView(DeleteViewTestMixin, WebTestStaffMode):
    url = reverse("staff:questionnaire_delete")
    model_cls = Questionnaire
    permission_method_to_patch = (Questionnaire, "can_be_deleted_by_manager")

    @classmethod
    def get_post_params(cls):
        return {"questionnaire_id": cls.instance.pk}


class TestQuestionnaireUpdateIndicesView(WebTestStaffMode):
    url = reverse("staff:questionnaire_update_indices")
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.questionnaire1 = baker.make(Questionnaire, order=7)
        cls.questionnaire2 = baker.make(Questionnaire, order=8)
        cls.manager = make_manager()

        cls.post_params = {cls.questionnaire1.id: 0, cls.questionnaire2.id: 1}

    def test_update_indices(self):
        self.app.post(self.url, user=self.manager, params=self.post_params, status=200)

        self.questionnaire1.refresh_from_db()
        self.questionnaire2.refresh_from_db()
        self.assertEqual(self.questionnaire1.order, 0)
        self.assertEqual(self.questionnaire2.order, 1)

    def test_invalid_parameters(self):
        # invalid ids
        params = {"133742": 0, self.questionnaire2.id: 1}
        self.app.post(self.url, user=self.manager, params=params, status=404)
        params = {"asd": 0, self.questionnaire2.id: 1}
        self.app.post(self.url, user=self.manager, params=params, status=400)
        params = {None: 0, self.questionnaire2.id: 1}
        self.app.post(self.url, user=self.manager, params=params, status=400)

        # invalid values
        with assert_no_database_modifications():
            params = {self.questionnaire1.id: "asd", self.questionnaire2.id: 1}
            self.app.post(self.url, user=self.manager, params=params, status=400)

        # correct parameters
        params = {self.questionnaire1.id: 0, self.questionnaire2.id: 1}
        self.app.post(self.url, user=self.manager, params=params, status=200)


class TestQuestionnaireVisibilityView(WebTestStaffMode):
    url = reverse("staff:questionnaire_visibility")
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.questionnaire = baker.make(Questionnaire, visibility=Questionnaire.Visibility.MANAGERS)
        cls.manager = make_manager()

    def test_set_visibility(self):
        post_params = {"questionnaire_id": self.questionnaire.id, "visibility": Questionnaire.Visibility.EDITORS}
        self.app.post(self.url, user=self.manager, params=post_params, status=200)

        self.questionnaire.refresh_from_db()
        self.assertEqual(self.questionnaire.visibility, Questionnaire.Visibility.EDITORS)

    def test_invalid_visibility(self):
        post_params = {"questionnaire_id": self.questionnaire.id, "visibility": ""}
        self.app.post(self.url, user=self.manager, params=post_params, status=400)

        post_params = {"questionnaire_id": self.questionnaire.id, "visibility": "123"}
        self.app.post(self.url, user=self.manager, params=post_params, status=400)

        post_params = {"questionnaire_id": self.questionnaire.id, "visibility": "asd"}
        self.app.post(self.url, user=self.manager, params=post_params, status=400)

        self.questionnaire.refresh_from_db()
        self.assertEqual(self.questionnaire.visibility, Questionnaire.Visibility.MANAGERS)


class TestQuestionnaireSetLockedView(WebTestStaffMode):
    url = reverse("staff:questionnaire_set_locked")
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.questionnaire = baker.make(Questionnaire, visibility=Questionnaire.Visibility.MANAGERS)
        cls.manager = make_manager()

    def test_set_is_locked(self):
        self.questionnaire.is_locked = False
        self.questionnaire.save()

        post_params = {"questionnaire_id": self.questionnaire.id, "is_locked": "1"}
        self.app.post(self.url, user=self.manager, params=post_params, status=200)
        self.questionnaire.refresh_from_db()
        self.assertTrue(self.questionnaire.is_locked)

        post_params = {"questionnaire_id": self.questionnaire.id, "is_locked": "0"}
        self.app.post(self.url, user=self.manager, params=post_params, status=200)
        self.questionnaire.refresh_from_db()
        self.assertFalse(self.questionnaire.is_locked)

    def test_invalid_parameters(self):
        post_params = {"questionnaire_id": self.questionnaire.id, "is_locked": ""}
        self.app.post(self.url, user=self.manager, params=post_params, status=400)

        post_params = {"questionnaire_id": self.questionnaire.id, "is_locked": "asd"}
        self.app.post(self.url, user=self.manager, params=post_params, status=400)


class TestCourseTypeView(WebTestStaffMode):
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
        CourseType.objects.create(name_de="uZJcsl0rNc", name_en="uZJcsl0rNc")
        page = self.app.get(self.url, user=self.manager, status=200)
        self.assertIn("uZJcsl0rNc", page)

    def test_course_type_form(self):
        """
        Adds a course type via the staff form and verifies that the type was created in the db.
        """
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["course-type-form"]
        form["form-0-name_de"].value = "Vorlesung"
        form["form-0-name_en"].value = "Lecture"
        self.set_import_names(form["form-0-import_names"], ["Vorlesung", "V"])
        response = form.submit().follow()
        self.assertContains(response, "Successfully")

        self.assertEqual(CourseType.objects.count(), 1)
        self.assertTrue(
            CourseType.objects.filter(name_de="Vorlesung", name_en="Lecture", import_names=["Vorlesung", "V"]).exists()
        )

    def test_import_names_duplicated_error(self):
        baker.make(CourseType, _bulk_create=True, _quantity=2)
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["course-type-form"]
        self.set_import_names(form["form-0-import_names"], ["Vorlesung", "v"])
        self.set_import_names(form["form-1-import_names"], ["Veranstaltung", "V"])
        response = form.submit()
        self.assertContains(response, "Import name &quot;V&quot; is duplicated. Import names are not case sensitive.")


class TestCourseTypeMergeSelectionView(WebTestStaffMode):
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


class TestCourseTypeMergeView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.main_type = baker.make(CourseType, name_en="A course type", import_names=["M"])
        cls.other_type = baker.make(CourseType, name_en="Obsolete course type", import_names=["O"])
        baker.make(Course, type=cls.main_type)
        baker.make(Course, type=cls.other_type)

        cls.url = f"/staff/course_types/{cls.main_type.pk}/merge/{cls.other_type.pk}"

    def test_merge_works(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["course-type-merge-form"]
        response = form.submit().follow()
        self.assertIn("Successfully", str(response))

        self.assertFalse(CourseType.objects.filter(name_en="Obsolete course type").exists())
        self.main_type.refresh_from_db()
        self.assertEqual(self.main_type.import_names, ["M", "O"])
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
            state=Evaluation.State.IN_EVALUATION,
        )
        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=top_general_questionnaire, type=QuestionType.POSITIVE_LIKERT)
        cls.text_question = baker.make(Question, questionnaire=top_general_questionnaire, type=QuestionType.TEXT)
        cls.evaluation.general_contribution.questionnaires.set([top_general_questionnaire])

    def assert_transition(
        self,
        action: str,
        old_decision: TextAnswer.ReviewDecision,
        expected_new_decision: TextAnswer.ReviewDecision | Literal["unchanged"] = "unchanged",
        *,
        status: int = 204,
    ):
        expected_new_decision = old_decision if expected_new_decision == "unchanged" else expected_new_decision

        with run_in_staff_mode(self):
            textanswer = baker.make(TextAnswer, contribution__evaluation=self.evaluation, review_decision=old_decision)
            params = {"answer_id": textanswer.id, "action": action}
            response = self.app.post(self.url, params=params, user=self.manager, status=status)

            textanswer.refresh_from_db()
            self.assertEqual(textanswer.review_decision, expected_new_decision)
            return response

    def test_review_actions(self):
        # in an evaluation with only one voter reviewing should fail
        self.assert_transition("publish", TextAnswer.ReviewDecision.UNDECIDED, status=403)

        let_user_vote_for_evaluation(self.student2, self.evaluation)

        # now reviewing should work
        self.assert_transition("publish", TextAnswer.ReviewDecision.UNDECIDED, TextAnswer.ReviewDecision.PUBLIC)
        self.assert_transition("delete", TextAnswer.ReviewDecision.UNDECIDED, TextAnswer.ReviewDecision.DELETED)
        self.assert_transition("make_private", TextAnswer.ReviewDecision.UNDECIDED, TextAnswer.ReviewDecision.PRIVATE)
        self.assert_transition("unreview", TextAnswer.ReviewDecision.PUBLIC, TextAnswer.ReviewDecision.UNDECIDED)

        # textanswer_edit action should not change the state, but give a link to edit page
        response = self.assert_transition(
            "textanswer_edit",
            TextAnswer.ReviewDecision.UNDECIDED,
            status=302,
        )
        self.assertRegex(response.location, r"/staff/textanswer/[0-9a-f\-]+/edit$")

    def test_invalid_action(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        self.assert_transition("", TextAnswer.ReviewDecision.UNDECIDED, status=400)
        self.assert_transition("123", TextAnswer.ReviewDecision.UNDECIDED, status=400)
        self.assert_transition("dummy", TextAnswer.ReviewDecision.UNDECIDED, status=400)

    def test_finishing_review_updates_results(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation, create_answers=True)
        self.evaluation.end_evaluation()
        self.evaluation.can_publish_text_results = True
        self.evaluation.save()
        results = get_results(self.evaluation)

        textresult = next(
            result for result in results.questionnaire_results[0].question_results if isinstance(result, TextResult)
        )
        self.assertEqual(len(textresult.answers), 0)

        textanswer = self.evaluation.unreviewed_textanswer_set[0]
        textanswer.review_decision = TextAnswer.ReviewDecision.PUBLIC
        textanswer.save()
        self.evaluation.end_review()
        self.evaluation.save()
        results = get_results(self.evaluation)

        textresult = next(
            result for result in results.questionnaire_results[0].question_results if isinstance(result, TextResult)
        )
        self.assertEqual(len(textresult.answers), 1)

    def test_published(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        self.assert_transition("publish", TextAnswer.ReviewDecision.UNDECIDED, TextAnswer.ReviewDecision.PUBLIC)
        Evaluation.objects.filter(id=self.evaluation.id).update(state=Evaluation.State.PUBLISHED)
        self.assert_transition("publish", TextAnswer.ReviewDecision.UNDECIDED, status=403)

    def test_archived(self):
        let_user_vote_for_evaluation(self.student2, self.evaluation)
        self.assert_transition("publish", TextAnswer.ReviewDecision.UNDECIDED, TextAnswer.ReviewDecision.PUBLIC)
        Semester.objects.filter(id=self.evaluation.course.semester.id).update(results_are_archived=True)
        self.assert_transition("publish", TextAnswer.ReviewDecision.UNDECIDED, status=403)


class TestEvaluationTextanswersUpdateFlagView(WebTest):
    url = reverse("staff:evaluation_textanswers_update_flag")
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.answer = baker.make(TextAnswer, contribution__evaluation__can_publish_text_results=True)

    def test_post_update(self):
        with run_in_staff_mode(self):
            self.assertFalse(self.answer.is_flagged)

            # Add flag
            self.app.post(
                self.url,
                user=self.manager,
                status=204,
                params={"answer_id": self.answer.pk, "is_flagged": "true"},
            )
            self.answer.refresh_from_db()
            self.assertTrue(self.answer.is_flagged)

            # Do it again
            self.app.post(
                self.url,
                user=self.manager,
                status=204,
                params={"answer_id": self.answer.pk, "is_flagged": "true"},
            )
            self.answer.refresh_from_db()
            self.assertTrue(self.answer.is_flagged)

            # Remove flag
            self.app.post(
                self.url,
                user=self.manager,
                status=204,
                params={"answer_id": self.answer.pk, "is_flagged": "false"},
            )
            self.answer.refresh_from_db()
            self.assertFalse(self.answer.is_flagged)

    def test_unknown_values(self):
        with run_in_staff_mode(self):
            self.app.post(self.url, user=self.manager, status=400, params={"answer_id": self.answer.pk})
            self.answer.refresh_from_db()
            self.assertFalse(self.answer.is_flagged)

            def helper(is_flagged_str, expect_success):
                self.app.post(
                    self.url,
                    user=self.manager,
                    status=204 if expect_success else 400,
                    params={"answer_id": self.answer.pk, "is_flagged": is_flagged_str},
                )
                self.answer.refresh_from_db()
                self.assertEqual(self.answer.is_flagged, expect_success)

            for is_flagged_str, expect_success in [("True", False), ("False", False), ("", False), ("true", True)]:
                helper(is_flagged_str, expect_success)


class TestEvaluationTextAnswersSkip(WebTestStaffMode):
    csrf_checks = False
    url = reverse("staff:evaluation_textanswers_skip")

    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(UserProfile, _fill_optional=["email"], groups=[Group.objects.get(name="Reviewer")])
        cls.evaluation = baker.make(Evaluation, state=Evaluation.State.IN_EVALUATION, can_publish_text_results=True)

    def test_skip(self):
        params = {"evaluation_id": self.evaluation.pk}
        response = self.app.post(self.url, user=self.user, status=200, params=params)
        self.assertEqual(response.client.session["review-skipped"], {self.evaluation.id})


class ParticipationArchivingTests(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_raise_403(self):
        """
        Tests whether inaccessible views on semesters/evaluations with
        archived participations correctly raise a 403.
        """
        semester = baker.make(Semester, participations_are_archived=True)
        evaluation = baker.make(Evaluation, course__semester=semester)

        urls = [
            reverse("staff:semester_import", args=[semester.pk]),
            reverse("staff:semester_questionnaire_assign", args=[semester.pk]),
            reverse("staff:evaluation_create_for_semester", args=[semester.pk]),
            f"{reverse('staff:evaluation_operation', args=[semester.pk])}?evaluation={evaluation.pk}",
        ]

        for url in urls:
            self.app.get(url, user=self.manager, status=403)


class TestTemplateEditView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.template = EmailTemplate.objects.first()

    def test_emailtemplate(self):
        page = self.app.get(f"/staff/template/{self.template.pk}", user=self.manager, status=200)

        form = page.forms["template-form"]
        form["subject"] = "subject: mflkd862xmnbo5"
        form["plain_content"] = "plain_content: mflkd862xmnbo5"
        form["html_content"] = "html_content: <p>mflkd862xmnbo5</p>"
        form.submit()

        self.template.refresh_from_db()
        self.assertEqual(self.template.plain_content, "plain_content: mflkd862xmnbo5")
        self.assertEqual(self.template.html_content, "html_content: <p>mflkd862xmnbo5</p>")

        form["plain_content"] = " invalid tag: {{}}"
        form.submit()
        self.template.refresh_from_db()
        self.assertEqual(self.template.plain_content, "plain_content: mflkd862xmnbo5")
        self.assertEqual(self.template.html_content, "html_content: <p>mflkd862xmnbo5</p>")

        form["html_content"] = " invalid tag: {{}}"
        form.submit()
        self.template.refresh_from_db()
        self.assertEqual(self.template.plain_content, "plain_content: mflkd862xmnbo5")
        self.assertEqual(self.template.html_content, "html_content: <p>mflkd862xmnbo5</p>")

    def test_available_variables(self):
        # We want to trigger all paths to ensure there are no syntax errors.
        expected_variables = {
            EmailTemplate.STUDENT_REMINDER: "first_due_in_days",
            EmailTemplate.EDITOR_REVIEW_NOTICE: "evaluations",
            EmailTemplate.TEXT_ANSWER_REVIEW_REMINDER: "evaluation_url_tuples",
            EmailTemplate.EVALUATION_STARTED: "due_evaluations",
            EmailTemplate.DIRECT_DELEGATION: "delegate_user",
        }

        for name, variable in expected_variables.items():
            template = EmailTemplate.objects.get(name=name)
            page = self.app.get(f"/staff/template/{template.pk}", user=self.manager, status=200)
            self.assertContains(page, variable)


class TestTextAnswerWarningsView(WebTestStaffMode):
    url = "/staff/text_answer_warnings/"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_text_answer_warnings_form(self):
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["text-answer-warnings-form"]
        last_form_id = 0
        helper_set_dynamic_choices_field_value(form[f"form-{last_form_id}-trigger_strings"], ["x"])
        form[f"form-{last_form_id}-warning_text_de"].value = "Ein Wort mit X"
        form[f"form-{last_form_id}-warning_text_en"].value = "A word with X"
        response = form.submit().follow()
        self.assertContains(response, "Successfully")

        self.assertEqual(TextAnswerWarning.objects.count(), 1)
        self.assertTrue(
            TextAnswerWarning.objects.filter(
                trigger_strings=["x"],
                warning_text_de="Ein Wort mit X",
                warning_text_en="A word with X",
            ).exists()
        )


class TestDegreeView(WebTestStaffMode):
    url = "/staff/degrees/"

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_degree_form(self):
        """
        Adds a degree via the staff form and verifies that the degree was created in the db.
        """
        degree_count_before = Degree.objects.count()
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["degree-form"]
        last_form_id = int(form["form-TOTAL_FORMS"].value) - 1
        form[f"form-{last_form_id}-name_de"].value = "Diplom"
        form[f"form-{last_form_id}-name_en"].value = "Diploma"
        helper_set_dynamic_choices_field_value(form[f"form-{last_form_id}-import_names"], ["Diplom", "D"])
        response = form.submit().follow()
        self.assertContains(response, "Successfully")

        self.assertEqual(Degree.objects.count(), degree_count_before + 1)
        self.assertTrue(
            Degree.objects.filter(
                name_de="Diplom",
                name_en="Diploma",
                import_names=["Diplom", "D"],
            ).exists()
        )

    def test_import_names_duplicated_error(self):
        baker.make(Degree, _bulk_create=True, _quantity=2)
        page = self.app.get(self.url, user=self.manager, status=200)
        form = page.forms["degree-form"]
        helper_set_dynamic_choices_field_value(form["form-0-import_names"], ["Master of Arts", "M"])
        helper_set_dynamic_choices_field_value(form["form-1-import_names"], ["Master of Science", "M"])
        response = form.submit()
        self.assertContains(response, "Import name &quot;M&quot; is duplicated.")


class TestSemesterQuestionnaireAssignment(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        semester = baker.make(Semester)
        cls.url = f"/staff/semester/{semester.pk}/assign"

        cls.course_type_1 = baker.make(CourseType)
        cls.course_type_2 = baker.make(CourseType)
        cls.responsible = baker.make(UserProfile)
        cls.questionnaire_1 = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        cls.questionnaire_2 = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        cls.questionnaire_responsible = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        cls.evaluation_1 = baker.make(
            Evaluation,
            course=baker.make(Course, semester=semester, type=cls.course_type_1, responsibles=[cls.responsible]),
        )
        cls.evaluation_2 = baker.make(
            Evaluation,
            course=baker.make(Course, semester=semester, type=cls.course_type_2, responsibles=[cls.responsible]),
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
        form["all-contributors"] = [self.questionnaire_responsible.pk]

        response = form.submit().follow()
        self.assertIn("Successfully", str(response))

        self.assertEqual(
            set(self.evaluation_1.general_contribution.questionnaires.all()),
            {self.questionnaire_1, self.questionnaire_2},
        )
        self.assertEqual(set(self.evaluation_2.general_contribution.questionnaires.all()), {self.questionnaire_2})
        self.assertEqual(
            set(self.evaluation_1.contributions.get(contributor=self.responsible).questionnaires.all()),
            {self.questionnaire_responsible},
        )
        self.assertEqual(
            set(self.evaluation_2.contributions.get(contributor=self.responsible).questionnaires.all()),
            {self.questionnaire_responsible},
        )


class TestSemesterActiveStateBehaviour(WebTestStaffMode):
    url = "/staff/semester/make_active"
    csrf_checks = False

    def test_make_other_semester_active(self):
        manager = make_manager()
        semester1 = baker.make(Semester, is_active=True)
        semester2 = baker.make(Semester, is_active=False)

        self.app.post(self.url, user=manager, status=200, params={"semester_id": semester2.id})

        semester1.refresh_from_db()
        semester2.refresh_from_db()

        self.assertFalse(semester1.is_active)
        self.assertTrue(semester2.is_active)


class TestStaffMode(WebTest):
    url_enter = "/staff/enter_staff_mode"
    url_exit = "/staff/exit_staff_mode"

    some_staff_url = "/staff/degrees/"

    csrf_checks = False

    def test_staff_mode(self):
        manager = make_manager()

        response = self.app.post(self.url_enter, user=manager).follow().follow()
        self.assertTrue("staff_mode_start_time" in self.app.session)
        self.assertContains(response, "Users")

        self.app.get(self.some_staff_url, user=manager, status=200)

        response = self.app.post(self.url_exit, user=manager).follow().follow()
        self.assertFalse("staff_mode_start_time" in self.app.session)
        self.assertNotContains(response, "Users")

        self.app.get(self.some_staff_url, user=manager, status=403)

    def test_staff_permission_required(self):
        student_user = baker.make(UserProfile, email="student@institution.example.com")
        self.app.post(self.url_enter, user=student_user, status=403)
        self.app.post(self.url_exit, user=student_user, status=403)
