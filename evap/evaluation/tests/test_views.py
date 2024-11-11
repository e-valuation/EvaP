from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from model_bakery import baker

from evap.evaluation.models import Evaluation, Question, QuestionType, Semester, UserProfile
from evap.evaluation.tests.tools import (
    WebTest,
    WebTestWith200Check,
    create_evaluation_with_responsible_and_editor,
    make_manager,
    store_ts_test_asset,
)
from evap.staff.tests.utils import WebTestStaffMode


class RenderJsTranslationCatalog(WebTest):
    url = reverse("javascript-catalog")

    def render_pages(self):
        # Not using render_pages decorator to manually create a single (special) javascript file
        content = self.app.get(self.url).content
        store_ts_test_asset("catalog.js", content)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TestIndexView(WebTest):
    url = "/"

    @override_settings(ACTIVATE_OPEN_ID_LOGIN=False)
    def test_login_for_staff_users_correctly_redirects(self):
        """Regression test for #1523: Access denied on manager login"""
        internal_email = (
            "manager@institution.example.com"  # external users don't necessarily have a proper redirect page
        )
        baker.make(
            UserProfile,
            email=internal_email,
            password=make_password("evap"),
            groups=[Group.objects.get(name="Manager")],
        )

        response = self.app.get(self.url)
        password_form = response.forms["email-login-form"]
        password_form["email"] = internal_email
        password_form["password"] = "evap"
        response = password_form.submit()
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertRedirects(response.follow(), "/results/")

    @override_settings(ACTIVATE_OPEN_ID_LOGIN=False)
    def test_login_view_respects_redirect_parameter(self):
        """Regression test for #1658: redirect after login"""
        internal_email = "manager@institution.example.com"
        baker.make(
            UserProfile,
            email=internal_email,
            password=make_password("evap"),
        )

        response = self.app.get(self.url + "?next=/test42/")
        password_form = response.forms["email-login-form"]
        password_form["email"] = internal_email
        password_form["password"] = "evap"
        response = password_form.submit()
        self.assertRedirects(response.follow(), "/test42/", fetch_redirect_response=False)

    def test_send_new_login_key(self):
        """Tests whether requesting a new login key is only possible for existing users,
        shows the expected success message and sends only one email to the requesting
        user without people in cc even if the user has delegates and cc users."""
        baker.make(UserProfile, email="asdf@example.com")
        response = self.app.get(self.url)
        email_form = response.forms["request-login-form"]
        email_form["email"] = "doesnotexist@example.com"
        self.assertIn("No user with this email address was found", email_form.submit())
        email = "asdf@example.com"
        email_form["email"] = email
        self.assertIn("We sent you", email_form.submit().follow())
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].to == [email])
        self.assertEqual(len(mail.outbox[0].cc), 0)


class TestStartpage(WebTest):
    def test_default_startpage(self):
        result = create_evaluation_with_responsible_and_editor()
        responsible = result["responsible"]
        evaluation = result["evaluation"]

        evaluation.participants.add(responsible)

        self.assertRedirects(self.app.get(reverse("evaluation:index"), user=responsible), reverse("student:index"))

        page = self.app.get(reverse("contributor:index"), user=responsible)
        form = page.forms["startpage-form"]
        form.submit()

        self.assertRedirects(self.app.get(reverse("evaluation:index"), user=responsible), reverse("contributor:index"))


class TestLegalNoticeView(WebTestWith200Check):
    url = "/legal_notice"
    test_users = [""]


class TestFAQView(WebTestWith200Check):
    url = "/faq"
    test_users = [""]


class TestContactEmail(WebTest):
    csrf_checks = False
    url = "/contact"

    @override_settings(ALLOW_ANONYMOUS_FEEDBACK_MESSAGES=True)
    def test_sends_mail(self):
        user = baker.make(UserProfile, email="user@institution.example.com")
        # normal email
        self.app.post(
            self.url,
            params={"message": "feedback message", "title": "some title", "anonymous": "false"},
            user=user,
        )
        # anonymous email
        self.app.post(
            self.url,
            params={"message": "feedback message", "title": "some title", "anonymous": "true"},
            user=user,
        )

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].reply_to, ["user@institution.example.com"])
        self.assertEqual(mail.outbox[1].reply_to, [])

    @override_settings(ALLOW_ANONYMOUS_FEEDBACK_MESSAGES=False)
    def test_anonymous_not_allowed(self):
        user = baker.make(UserProfile, email="user@institution.example.com")
        self.app.post(
            self.url,
            params={"message": "feedback message", "title": "some title", "anonymous": "true"},
            user=user,
            status=400,
        )
        self.assertEqual(len(mail.outbox), 0)


class TestChangeLanguageView(WebTest):
    url = "/set_lang"
    csrf_checks = False

    def test_changes_language(self):
        user = baker.make(UserProfile, email="tester@institution.example.com", language="de")

        self.app.post(self.url, params={"language": "en"}, user=user)

        user.refresh_from_db()
        self.assertEqual(user.language, "en")


class TestProfileView(WebTest):
    url = reverse("evaluation:profile_edit")

    @classmethod
    def setUpTestData(cls):
        result = create_evaluation_with_responsible_and_editor()
        cls.responsible = result["responsible"]

    def test_requires_login(self):
        response = self.app.get(self.url, user=None, status=302)
        self.assertRedirects(response, f"/?next={self.url}", fetch_redirect_response=False)

    def test_save_settings(self):
        user = baker.make(UserProfile)
        page = self.app.get(self.url, user=self.responsible)
        form = page.forms["profile-form"]
        form["delegates"] = [user.pk]
        form.submit()

        self.responsible.refresh_from_db()
        self.assertEqual(list(self.responsible.delegates.all()), [user])

    def test_view_settings_as_non_editor(self):
        user = baker.make(UserProfile, email="testuser@example.com")
        page = self.app.get(self.url, user=user)
        self.assertIn("Personal information", page)
        self.assertNotIn("Delegates", page)
        self.assertIn(user.email, page)

    def test_edit_display_name(self):
        page = self.app.get(self.url, user=self.responsible)
        self.assertNotContains(page, "testdisplayname")
        self.assertFalse(UserProfile.objects.filter(first_name_chosen="testdisplayname").exists())

        form = page.forms["profile-form"]
        form["first_name_chosen"] = "testdisplayname"
        form.submit()
        self.assertTrue(UserProfile.objects.filter(first_name_chosen="testdisplayname").exists())

        page = self.app.get(self.url, user=self.responsible)
        self.assertContains(page, "testdisplayname")


class TestNegativeLikertQuestions(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.voting_user = baker.make(UserProfile, email="voting_user1@institution.example.com")

        cls.evaluation = baker.make(
            Evaluation,
            participants=[cls.voting_user],
            state=Evaluation.State.IN_EVALUATION,
        )

        cls.question = baker.make(
            Question,
            type=QuestionType.NEGATIVE_LIKERT,
            text_en="Negative Likert Question",
            text_de="Negative Likert Frage",
        )

        cls.evaluation.general_contribution.questionnaires.add(cls.question.questionnaire)

        cls.url = reverse("student:vote", args=[cls.evaluation.pk])

    def test_answer_ordering(self):
        page = self.app.get(self.url, user=self.voting_user, status=200).body.decode()
        self.assertLess(page.index("Strongly<br>disagree"), page.index("Strongly<br>agree"))


class TestNotebookView(WebTest):
    url = reverse("evaluation:profile_edit")  # is used exemplarily, notebook is accessed from all pages
    note = "Data is so beautiful"

    def test_notebook(self):
        user = baker.make(UserProfile, email="student@institution.example.com")

        page = self.app.get(self.url, user=user)
        form = page.forms["notebook-form"]
        form["notes"] = self.note
        form.submit()

        user.refresh_from_db()
        self.assertEqual(user.notes, self.note)


class TestResetEvaluation(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.url = reverse("staff:semester_view", args=[cls.semester.pk])

    def reset_from_x_to_new(self, x: Evaluation.State, success_expected: bool) -> None:
        evaluation = baker.make(Evaluation, state=x, course__semester=self.semester)

        semester_overview_page = self.app.get(self.url, user=self.manager, status=200)
        form = semester_overview_page.forms["evaluation_operation_form"]
        form["evaluation"] = [evaluation.pk]
        confirmation_page = form.submit(name="target_state", value=str(Evaluation.State.NEW))

        if success_expected:
            confirmation_page.forms["evaluation-operation-form"].submit()
            self.assertEqual(Evaluation.objects.get(pk=evaluation.pk).state, Evaluation.State.NEW)
        else:
            self.assertEqual(Evaluation.objects.get(pk=evaluation.pk).state, x)
            self.assertNotEqual(confirmation_page.status_int, 200)

    def test_reset_to_new(self) -> None:
        invalid_start_states = [Evaluation.State.NEW, Evaluation.State.PUBLISHED]

        valid_start_states = [
            Evaluation.State.PREPARED,
            Evaluation.State.EDITOR_APPROVED,
            Evaluation.State.APPROVED,
            Evaluation.State.IN_EVALUATION,
            Evaluation.State.EVALUATED,
            Evaluation.State.REVIEWED,
        ]

        for s in valid_start_states:
            self.reset_from_x_to_new(s, success_expected=True)
        for s in invalid_start_states:
            self.reset_from_x_to_new(s, success_expected=False)
