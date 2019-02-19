from django.core import mail

from django_webtest import WebTest
from model_mommy import mommy

from evap.evaluation.models import Evaluation, UserProfile, Contribution
from evap.evaluation.tests.tools import WebTestWith200Check, create_evaluation_with_responsible_and_editor

TESTING_COURSE_ID = 2


class TestContributorDirectDelegationView(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.evaluation = mommy.make(Evaluation, state='prepared')

        cls.editor = mommy.make(UserProfile)
        cls.non_editor = mommy.make(UserProfile, email="a@b.c")
        mommy.make(Contribution, evaluation=cls.evaluation, contributor=cls.editor, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)

    def test_direct_delegation_request(self):
        data = {"delegate_to": self.non_editor.id}
        page = self.app.post('/contributor/evaluation/{}/direct_delegation'.format(self.evaluation.id), params=data, user=self.editor).follow()

        self.assertContains(
            page,
            '{} was added as a contributor for evaluation &quot;{}&quot; and was sent an email with further information.'.format(str(self.non_editor), str(self.evaluation))
        )

        contribution = Contribution.objects.get(contributor=self.non_editor)
        self.assertTrue(contribution.can_edit)

        self.assertEqual(len(mail.outbox), 1)

    def test_direct_delegation_request_with_existing_contribution(self):
        contribution = mommy.make(Contribution, evaluation=self.evaluation, contributor=self.non_editor, can_edit=False)
        old_contribution_count = Contribution.objects.count()

        data = {"delegate_to": self.non_editor.id}
        page = self.app.post('/contributor/evaluation/{}/direct_delegation'.format(self.evaluation.id), params=data, user=self.editor).follow()

        self.assertContains(
            page,
            '{} was added as a contributor for evaluation &quot;{}&quot; and was sent an email with further information.'.format(str(self.non_editor), str(self.evaluation))
        )

        self.assertEqual(Contribution.objects.count(), old_contribution_count)

        contribution.refresh_from_db()
        self.assertTrue(contribution.can_edit)

        self.assertEqual(len(mail.outbox), 1)


class TestContributorView(WebTestWith200Check):
    url = '/contributor/'
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        create_evaluation_with_responsible_and_editor()


class TestContributorSettingsView(WebTest):
    url = '/contributor/settings'

    @classmethod
    def setUpTestData(cls):
        create_evaluation_with_responsible_and_editor()

    def test_save_settings(self):
        user = mommy.make(UserProfile)
        page = self.app.get(self.url, user="responsible", status=200)
        form = page.forms["settings-form"]
        form["delegates"] = [user.pk]
        form.submit()

        self.assertEqual(list(UserProfile.objects.get(username='responsible').delegates.all()), [user])


class TestContributorEvaluationView(WebTestWith200Check):
    url = '/contributor/evaluation/%s' % TESTING_COURSE_ID
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        create_evaluation_with_responsible_and_editor(evaluation_id=TESTING_COURSE_ID)

    def setUp(self):
        self.evaluation = Evaluation.objects.get(pk=TESTING_COURSE_ID)

    def test_wrong_state(self):
        self.evaluation.revert_to_new()
        self.evaluation.save()
        self.app.get(self.url, user='responsible', status=403)

    def test_information_message(self):
        self.evaluation.editor_approve()
        self.evaluation.save()

        page = self.app.get(self.url, user='editor')
        self.assertContains(page, "You cannot edit this evaluation because it has already been approved")
        self.assertNotContains(page, "Please review the evaluation's details below, add all contributors and select suitable questionnaires. Once everything is okay, please approve the evaluation on the bottom of the page.")


class TestContributorEvaluationPreviewView(WebTestWith200Check):
    url = '/contributor/evaluation/%s/preview' % TESTING_COURSE_ID
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        create_evaluation_with_responsible_and_editor(evaluation_id=TESTING_COURSE_ID)

    def setUp(self):
        self.evaluation = Evaluation.objects.get(pk=TESTING_COURSE_ID)

    def test_wrong_state(self):
        self.evaluation.revert_to_new()
        self.evaluation.save()
        self.app.get(self.url, user='responsible', status=403)


class TestContributorEvaluationEditView(WebTest):
    url = '/contributor/evaluation/%s/edit' % TESTING_COURSE_ID

    @classmethod
    def setUpTestData(cls):
        create_evaluation_with_responsible_and_editor(evaluation_id=TESTING_COURSE_ID)

    def setUp(self):
        self.evaluation = Evaluation.objects.get(pk=TESTING_COURSE_ID)

    def test_not_authenticated(self):
        """
            Asserts that an unauthorized user gets redirected to the login page.
        """
        response = self.app.get(self.url)
        self.assertRedirects(response, '/?next=/contributor/evaluation/%s/edit' % TESTING_COURSE_ID)

    def test_wrong_usergroup(self):
        """
            Asserts that a user who is not part of the usergroup
            that is required for a specific view gets a 403.
            Regression test for #483
        """
        self.app.get(self.url, user='student', status=403)

    def test_wrong_state(self):
        """
            Asserts that a contributor attempting to edit an evaluation
            that is in a state where editing is not allowed gets a 403.
        """
        self.evaluation.editor_approve()
        self.evaluation.save()

        self.app.get(self.url, user='responsible', status=403)

    def test_contributor_evaluation_edit(self):
        """
            Tests whether the "save" button in the contributor's evaluation edit view does not
            change the evaluation's state, and that the "approve" button does that.
        """
        page = self.app.get(self.url, user="responsible", status=200)
        form = page.forms["evaluation-form"]
        form["vote_start_datetime"] = "2098-01-01 11:43:12"
        form["vote_end_date"] = "2099-01-01"

        form.submit(name="operation", value="save")
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.state, "prepared")

        form.submit(name="operation", value="approve")
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.state, "editor_approved")

        # test what happens if the operation is not specified correctly
        response = form.submit(expect_errors=True)
        self.assertEqual(response.status_code, 403)

    def test_contributor_evaluation_edit_preview(self):
        """
            Asserts that the preview button either renders a preview or shows an error.
        """
        page = self.app.get(self.url, user="responsible")
        form = page.forms["evaluation-form"]
        form["vote_start_datetime"] = "2099-01-01 11:43:12"
        form["vote_end_date"] = "2098-01-01"

        response = form.submit(name="operation", value="preview")
        self.assertNotIn("previewModal", response)
        self.assertIn("The preview could not be rendered", response)

        form["vote_start_datetime"] = "2098-01-01 11:43:12"
        form["vote_end_date"] = "2099-01-01"

        response = form.submit(name="operation", value="preview")
        self.assertIn("previewModal", response)
        self.assertNotIn("The preview could not be rendered", response)

    def test_contact_modal_escape(self):
        """
            Asserts that the evaluation title is correctly escaped in the contact modal.
            Regression test for #1060
        """
        self.evaluation.name_en = "Adam & Eve"
        self.evaluation.save()
        page = self.app.get(self.url, user="responsible", status=200)

        self.assertIn("changeParticipantRequestModalLabel", page)

        self.assertNotIn("Adam &amp;amp; Eve", page)
        self.assertIn("Adam &amp; Eve", page)
        self.assertNotIn("Adam & Eve", page)

    def test_information_message(self):
        page = self.app.get(self.url, user='editor')
        self.assertNotContains(page, "You cannot edit this evaluation because it has already been approved")
        self.assertContains(page, "Please review the evaluation's details below, add all contributors and select suitable questionnaires. Once everything is okay, please approve the evaluation on the bottom of the page.")

    def test_last_modified_on_formset_change(self):
        """
            Tests if last_modified_{user,time} is updated if only the contributor formset is changed
        """

        self.assertEqual(self.evaluation.last_modified_user, None)
        last_modified_time_before = self.evaluation.last_modified_time

        page = self.app.get(self.url, user='responsible', status=200)
        form = page.forms["evaluation-form"]

        # Change label of the first contribution
        form['contributions-0-label'] = 'test_label'
        form.submit(name="operation", value="approve")

        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.state, 'editor_approved')
        self.assertEqual(self.evaluation.last_modified_user.username, 'responsible')
        self.assertGreater(self.evaluation.last_modified_time, last_modified_time_before)

    def test_last_modified_unchanged(self):
        """
            Tests if last_modified_{user,time} stays the same when no values are changed in the form
        """
        self.assertIsNone(self.evaluation.last_modified_user)
        last_modified_time_before = self.evaluation.last_modified_time

        page = self.app.get(self.url, user='responsible', status=200)
        form = page.forms["evaluation-form"]
        form.submit(name="operation", value="approve")

        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.state, 'editor_approved')
        self.assertIsNone(self.evaluation.last_modified_user)
        self.assertEqual(self.evaluation.last_modified_time, last_modified_time_before)
