import xlrd
from django.core import mail
from django.urls import reverse
from model_bakery import baker

from evap.evaluation.models import Contribution, Course, Evaluation, Questionnaire, UserProfile
from evap.evaluation.tests.tools import (
    WebTest,
    WebTestWith200Check,
    create_evaluation_with_responsible_and_editor,
    render_pages,
    submit_with_modal,
)


class TestContributorDirectDelegationView(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.evaluation = baker.make(Evaluation, state=Evaluation.State.PREPARED)

        cls.editor = baker.make(UserProfile, email="editor@institution.example.com")
        cls.non_editor = baker.make(UserProfile, email="non_editor@institution.example.com")
        baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=cls.editor,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )

    def test_direct_delegation_request(self):
        data = {"delegate_to": self.non_editor.id}
        page = self.app.post(
            f"/contributor/evaluation/{self.evaluation.id}/direct_delegation",
            params=data,
            user=self.editor,
        ).follow()

        self.assertContains(
            page,
            f"{self.non_editor} was added as a contributor for evaluation &quot;{self.evaluation}&quot; and was sent an email with further information.",
        )

        contribution = Contribution.objects.get(contributor=self.non_editor)
        self.assertEqual(contribution.role, Contribution.Role.EDITOR)

        self.assertEqual(len(mail.outbox), 1)

    def test_direct_delegation_request_with_existing_contribution(self):
        contribution = baker.make(
            Contribution,
            evaluation=self.evaluation,
            contributor=self.non_editor,
            role=Contribution.Role.CONTRIBUTOR,
        )
        old_contribution_count = Contribution.objects.count()

        data = {"delegate_to": self.non_editor.id}
        page = self.app.post(
            f"/contributor/evaluation/{self.evaluation.id}/direct_delegation",
            params=data,
            user=self.editor,
        ).follow()

        self.assertContains(
            page,
            f"{self.non_editor} was added as a contributor for evaluation &quot;{self.evaluation}&quot; and was sent an email with further information.",
        )

        self.assertEqual(Contribution.objects.count(), old_contribution_count)

        contribution.refresh_from_db()
        self.assertEqual(contribution.role, Contribution.Role.EDITOR)

        self.assertEqual(len(mail.outbox), 1)


class TestContributorView(WebTestWith200Check):
    url = "/contributor/"

    @classmethod
    def setUpTestData(cls):
        users = create_evaluation_with_responsible_and_editor()
        cls.test_users = [users["editor"], users["responsible"]]


class TestContributorEvaluationView(WebTestWith200Check):
    @classmethod
    def setUpTestData(cls):
        result = create_evaluation_with_responsible_and_editor()
        cls.responsible = result["responsible"]
        cls.editor = result["editor"]
        cls.evaluation = result["evaluation"]

        cls.test_users = [cls.editor, cls.responsible]
        cls.url = f"/contributor/evaluation/{cls.evaluation.pk}"

    def test_wrong_state(self):
        self.evaluation.reset_to_new(delete_previous_answers=False)
        self.evaluation.save()
        self.app.get(self.url, user=self.responsible, status=403)

    def test_information_message(self):
        self.evaluation.editor_approve()
        self.evaluation.save()

        page = self.app.get(self.url, user=self.editor)
        self.assertContains(page, "You cannot edit this evaluation because it has already been approved")
        self.assertNotContains(
            page,
            "Please review the evaluation's details below, add all contributors and select suitable questionnaires. "
            "Once everything is okay, please approve the evaluation on the bottom of the page.",
        )


class TestContributorEvaluationPreviewView(WebTestWith200Check):
    @classmethod
    def setUpTestData(cls):
        result = create_evaluation_with_responsible_and_editor()
        cls.responsible = result["responsible"]
        cls.test_users = [result["editor"], result["responsible"]]
        cls.evaluation = result["evaluation"]
        cls.url = f"/contributor/evaluation/{cls.evaluation.pk}/preview"

    def test_wrong_state(self):
        self.evaluation.reset_to_new(delete_previous_answers=False)
        self.evaluation.save()
        self.app.get(self.url, user=self.responsible, status=403)

    def test_without_questionnaires_assigned(self):
        # regression test for #1747
        self.evaluation.general_contribution.questionnaires.set([])
        self.app.get(self.url, user=self.responsible, status=200)


class TestContributorEvaluationEditView(WebTest):
    render_pages_url = "/contributor/evaluation/PK/edit"

    @classmethod
    def setUpTestData(cls):
        result = create_evaluation_with_responsible_and_editor()
        cls.responsible = result["responsible"]
        cls.editor = result["editor"]
        cls.evaluation = result["evaluation"]
        cls.url = f"/contributor/evaluation/{cls.evaluation.pk}/edit"

    @render_pages
    def render_pages(self):
        self.evaluation.allow_editors_to_edit = False
        self.evaluation.save()

        content_without_allow_editors_to_edit = self.app.get(self.url, user=self.editor).content

        self.evaluation.allow_editors_to_edit = True
        self.evaluation.save()

        content_with_allow_editors_to_edit = self.app.get(self.url, user=self.editor).content

        return {
            "normal": content_without_allow_editors_to_edit,
            "allow_editors_to_edit": content_with_allow_editors_to_edit,
        }

    def test_not_authenticated(self):
        """
        Asserts that an unauthorized user gets redirected to the login page.
        """
        response = self.app.get(self.url)
        self.assertRedirects(response, f"/?next=/contributor/evaluation/{self.evaluation.pk}/edit")

    def test_wrong_usergroup(self):
        """
        Asserts that a user who is not part of the usergroup
        that is required for a specific view gets a 403.
        Regression test for #483
        """
        self.app.get(self.url, user="student@institution.example.com", status=403)

    def test_wrong_state(self):
        """
        Asserts that a contributor attempting to edit an evaluation
        that is in a state where editing is not allowed gets a 403.
        """
        self.evaluation.editor_approve()
        self.evaluation.save()

        self.app.get(self.url, user=self.responsible, status=403)

    def test_contributor_evaluation_edit(self):
        """
        Tests whether the "save" button in the contributor's evaluation edit view does not
        change the evaluation's state, and that the "approve" button does that.
        """
        page = self.app.get(self.url, user=self.responsible, status=200)
        form = page.forms["evaluation-form"]
        form["vote_start_datetime"] = "2098-01-01 11:43:12"
        form["vote_end_date"] = "2099-01-01"

        form.submit(name="operation", value="save")
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.state, Evaluation.State.PREPARED)

        submit_with_modal(page, form, name="operation", value="approve")
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        self.assertEqual(self.evaluation.state, Evaluation.State.EDITOR_APPROVED)

        # test what happens if the operation is not specified correctly
        form.submit(status=403)

    def test_single_locked_questionnaire(self):
        locked_questionnaire = baker.make(
            Questionnaire,
            type=Questionnaire.Type.TOP,
            is_locked=True,
            visibility=Questionnaire.Visibility.EDITORS,
        )
        responsible = UserProfile.objects.get(email="responsible@institution.example.com")
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, responsibles=[responsible]),
            state=Evaluation.State.PREPARED,
        )
        evaluation.general_contribution.questionnaires.set([locked_questionnaire])

        page = self.app.get(f"/contributor/evaluation/{evaluation.pk}/edit", user=responsible, status=200)
        form = page.forms["evaluation-form"]

        # see https://github.com/Pylons/webtest/issues/138
        for name_field_tuple in form.field_order[:]:
            if "disabled" in name_field_tuple[1].attrs:
                form.field_order.remove(name_field_tuple)

        response = form.submit(name="operation", value="save")
        self.assertIn("Successfully updated evaluation", response.follow())

    def test_contributor_evaluation_edit_preview(self):
        """
        Asserts that the preview button either renders a preview or shows an error.
        """
        page = self.app.get(self.url, user=self.responsible)
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
        page = self.app.get(self.url, user=self.responsible, status=200)

        self.assertIn("changeEvaluationRequestModalLabel", page)

        self.assertNotIn("Adam &amp;amp; Eve", page)
        self.assertIn("Adam &amp; Eve", page)
        self.assertNotIn("Adam & Eve", page)

    def test_information_message(self):
        page = self.app.get(self.url, user=self.editor)
        self.assertNotContains(page, "You cannot edit this evaluation because it has already been approved")
        self.assertContains(
            page,
            "Please review the evaluation's details below, add all contributors and select suitable questionnaires. "
            "Once everything is okay, please approve the evaluation on the bottom of the page.",
        )

    def test_display_request_buttons(self):
        self.evaluation.allow_editors_to_edit = False
        self.evaluation.save()
        page = self.app.get(self.url, user=self.responsible)
        self.assertEqual(page.body.decode().count("Request changes"), 1)
        self.assertEqual(page.body.decode().count("Request creation of new account"), 1)

        self.evaluation.allow_editors_to_edit = True
        self.evaluation.save()
        page = self.app.get(self.url, user=self.responsible)
        self.assertEqual(page.body.decode().count("Request changes"), 0)
        self.assertEqual(page.body.decode().count("Request creation of new account"), 2)


class TestContributorResultsExportView(WebTest):
    @classmethod
    def setUpTestData(cls):
        result = create_evaluation_with_responsible_and_editor()
        cls.url = reverse("contributor:export")
        cls.user = result["responsible"]

    def test_concise_header(self):
        response = self.app.get(self.url, user=self.user)

        workbook = xlrd.open_workbook(file_contents=response.content)
        self.assertEqual(workbook.sheets()[0].row_values(0)[0], f"Evaluation\n{self.user.full_name}")
