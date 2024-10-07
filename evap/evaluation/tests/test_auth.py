import urllib
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AnonymousUser, Group
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.test import override_settings
from django.urls import reverse
from django.views import View
from model_bakery import baker

from evap.evaluation import auth
from evap.evaluation.auth import class_or_function_check_decorator
from evap.evaluation.models import Contribution, Evaluation, UserProfile
from evap.evaluation.tests.tools import WebTest


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LoginTests(WebTest):
    csrf_checks = False
    url = reverse("evaluation:index")

    @classmethod
    def setUpTestData(cls):
        cls.external_user = baker.make(UserProfile, email="extern@extern.com")
        cls.external_user.ensure_valid_login_key()
        cls.inactive_external_user = baker.make(UserProfile, email="inactive@extern.com", is_active=False)
        cls.inactive_external_user.ensure_valid_login_key()
        evaluation = baker.make(Evaluation, state=Evaluation.State.PUBLISHED)
        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=iter([cls.external_user, cls.inactive_external_user]),
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            _quantity=2,
            _bulk_create=True,
        )

    @override_settings(PAGE_URL="https://example.com")
    def test_login_url_generation(self):
        generated_url = self.external_user.login_url
        self.assertEqual(generated_url, f"https://example.com/key/{self.external_user.login_key}")

        reversed_url = reverse("evaluation:login_key_authentication", args=[self.external_user.login_key])
        self.assertEqual(reversed_url, f"/key/{self.external_user.login_key}")

    def test_login_url_works(self):
        self.assertRedirects(self.app.get(reverse("contributor:index")), "/?next=/contributor/")

        url_with_key = reverse("evaluation:login_key_authentication", args=[self.external_user.login_key])
        old_login_key = self.external_user.login_key
        old_login_key_valid_until = self.external_user.login_key_valid_until
        page = self.app.get(url_with_key)
        self.external_user.refresh_from_db()
        self.assertEqual(old_login_key, self.external_user.login_key)
        self.assertEqual(old_login_key_valid_until, self.external_user.login_key_valid_until)
        self.assertContains(page, "Login")
        self.assertContains(page, self.external_user.full_name)

        page = self.app.post(url_with_key).follow().follow()
        self.assertEqual(page.context["user"], self.external_user)
        self.assertContains(page, "Logout")
        self.assertContains(page, self.external_user.full_name)

    def test_login_key_valid_only_once(self):
        page = self.app.get(reverse("evaluation:login_key_authentication", args=[self.external_user.login_key]))
        self.assertContains(page, self.external_user.full_name)

        url_with_key = reverse("evaluation:login_key_authentication", args=[self.external_user.login_key])
        page = self.app.post(url_with_key).follow().follow()
        self.assertEqual(page.context["user"], self.external_user)
        self.assertContains(page, "Logout")

        page = page.forms["logout-form"].submit().follow()
        self.assertIsInstance(page.context["user"], AnonymousUser)
        self.assertNotContains(page, "Logout")

        page = self.app.get(url_with_key).follow()
        self.assertContains(page, "The login URL is not valid anymore.")
        self.assertEqual(len(mail.outbox), 1)  # a new login key was sent

        new_key = UserProfile.objects.get(id=self.external_user.id).login_key
        page = self.app.post(reverse("evaluation:login_key_authentication", args=[new_key])).follow().follow()
        self.assertContains(page, self.external_user.full_name)

    def test_inactive_external_users_can_not_login(self):
        page = self.app.get(
            reverse("evaluation:login_key_authentication", args=[self.inactive_external_user.login_key])
        ).follow()
        self.assertContains(page, "Inactive users are not allowed to login")
        self.assertIsInstance(page.context["user"], AnonymousUser)
        self.assertNotContains(page, "Logout")

    def test_login_key_resend_if_still_valid(self):
        old_key = self.external_user.login_key
        page = self.app.post(self.url, params={"submit_type": "new_key", "email": self.external_user.email}).follow()
        new_key = UserProfile.objects.get(id=self.external_user.id).login_key

        self.assertEqual(old_key, new_key)
        self.assertEqual(len(mail.outbox), 1)  # a login key was sent
        self.assertContains(page, "We sent you an email with a one-time login URL. Please check your inbox.")

    @override_settings(
        OIDC_OP_AUTHORIZATION_ENDPOINT="https://oidc.example.com/auth",
        ACTIVATE_OPEN_ID_LOGIN=True,
    )
    def test_oidc_login(self):
        # This should send them to /oidc/authenticate
        page = self.app.get(self.url).click("Login")

        # which should then redirect them to OIDC_OP_AUTHORIZATION_ENDPOINT
        location = page.headers["location"]
        self.assertIn(settings.OIDC_OP_AUTHORIZATION_ENDPOINT, location)

        parse_result = urllib.parse.urlparse(location)
        parsed_query = urllib.parse.parse_qs(parse_result.query)

        self.assertIn("email", parsed_query["scope"][0].split(" "))
        self.assertIn("/oidc/callback/", parsed_query["redirect_uri"][0])

        state = parsed_query["state"][0]

        user = baker.make(UserProfile)
        # usually, the browser would now open that page and login. Then, they'd be redirected to /oidc/callback
        with patch.object(auth.OIDCAuthenticationBackend, "authenticate", return_value=user, __name__="authenticate"):
            page = self.app.get(f"/oidc/callback/?code=secret-code&state={state}")
            # The oidc module will now send a request to the oidc provider, asking whether the code is valid.
            # We've mocked the method that does that and will just return a UserProfile.

        # Thus, at this point, the user should be logged in and be redirected back to the start page.
        location = page.headers["location"]
        parse_result = urllib.parse.urlparse(location)
        self.assertEqual(parse_result.path, self.url)

        page = self.app.get(location)
        # A GET here should then redirect to the users real start page.
        # This should be a 403 since the user is external and has no course participation
        page = page.follow(status=403)

        self.assertIn("Logout", page.body.decode())
        self.assertEqual(page.context["user"], user)

    @override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
    def test_passworduser_login(self):
        """Tests whether a user can login with an incorrect and a correct password."""
        user = baker.make(UserProfile, email="user@example.com", password=make_password("evap"))

        # wrong password
        with override_settings(ACTIVATE_OPEN_ID_LOGIN=False):
            page = self.app.get(self.url)
            password_form = page.forms["email-login-form"]
            password_form["email"] = user.email
            password_form["password"] = "asd"  # nosec
            response = password_form.submit()
            self.assertIsInstance(response.context["user"], AnonymousUser)
            self.assertNotContains(response, "Logout")

        # correct password while password login is disabled
        with override_settings(ACTIVATE_OPEN_ID_LOGIN=True):
            self.assertFalse(auth.password_login_is_active())

            password_form["password"] = "evap"  # nosec
            response = password_form.submit(status=400)
            self.assertIsInstance(response.context["user"], AnonymousUser)
            self.assertNotContains(response, "Logout", status_code=400)

        # correct password while password login is enabled
        with override_settings(ACTIVATE_OPEN_ID_LOGIN=False):
            self.assertTrue(auth.password_login_is_active())

            response = password_form.submit(status=302).follow().follow()
            self.assertEqual(response.context["user"], user)
            self.assertContains(response, "Logout")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LoginTestsWithCSRF(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = baker.make(
            UserProfile, email="staff@institution.example.com", groups=[Group.objects.get(name="Manager")]
        )
        cls.staff_user_password = "staff"
        cls.staff_user.set_password(cls.staff_user_password)
        cls.staff_user.save()

    @override_settings(ACTIVATE_OPEN_ID_LOGIN=False)
    def test_entering_staff_mode_after_logout_and_login(self):
        """
        Asserts that managers can enter the staff mode after logging out and logging in again.
        Regression test for #1530.
        """
        page = self.app.get(reverse("evaluation:index"))
        form = page.forms["email-login-form"]
        form["email"] = self.staff_user.email
        form["password"] = self.staff_user_password
        page = form.submit().follow().follow()

        # staff user should now be logged in and see the logout button
        self.assertContains(page, "Logout")

        # log out user
        page = page.forms["logout-form"].submit().follow()
        self.assertNotContains(page, "Logout")

        # log user in again
        page = self.app.get(reverse("evaluation:index"))
        form = page.forms["email-login-form"]
        form["email"] = self.staff_user.email
        form["password"] = self.staff_user_password
        page = form.submit().follow().follow()

        # enter staff mode
        page = page.forms["enter-staff-mode-form"].submit().follow().follow()
        self.assertTrue("staff_mode_start_time" in self.app.session)
        self.assertContains(page, "Users")


class TestAuthDecorators(WebTest):
    @classmethod
    def setUpTestData(cls):
        @class_or_function_check_decorator
        def check_decorator(user: UserProfile) -> bool:
            return getattr(user, "some_condition")  # noqa: B009 # mocked later

        @check_decorator
        def function_based_view(_request):
            return HttpResponse()

        @check_decorator
        class ClassBasedView(View):
            def get(self, _request):
                return HttpResponse()

        cls.user = baker.make(UserProfile, email="testuser@institution.example.com")
        cls.function_based_view = function_based_view
        cls.class_based_view = ClassBasedView.as_view()

    @classmethod
    def make_request(cls):
        request = HttpRequest()
        request.method = "GET"
        request.user = cls.user
        return request

    @patch("evap.evaluation.models.UserProfile.some_condition", True, create=True)
    def test_passing_user_function_based(self):
        response = self.function_based_view(self.make_request())  # pylint: disable=too-many-function-args
        self.assertEqual(response.status_code, 200)

    @patch("evap.evaluation.models.UserProfile.some_condition", True, create=True)
    def test_passing_user_class_based(self):
        response = self.class_based_view(self.make_request())
        self.assertEqual(response.status_code, 200)

    @patch("evap.evaluation.models.UserProfile.some_condition", False, create=True)
    def test_failing_user_function_based(self):
        with self.assertRaises(PermissionDenied):
            self.function_based_view(self.make_request())  # pylint: disable=too-many-function-args

    @patch("evap.evaluation.models.UserProfile.some_condition", False, create=True)
    def test_failing_user_class_based(self):
        with self.assertRaises(PermissionDenied):
            self.class_based_view(self.make_request())
