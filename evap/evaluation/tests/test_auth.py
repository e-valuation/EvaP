import urllib
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from model_bakery import baker

from evap.evaluation import auth
from evap.evaluation.models import Contribution, Evaluation, UserProfile
from evap.evaluation.tests.tools import WebTest


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LoginTests(WebTest):
    csrf_checks = False

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
        self.assertContains(page, "Logout")
        self.assertContains(page, self.external_user.full_name)

    def test_login_key_valid_only_once(self):
        page = self.app.get(reverse("evaluation:login_key_authentication", args=[self.external_user.login_key]))
        self.assertContains(page, self.external_user.full_name)

        url_with_key = reverse("evaluation:login_key_authentication", args=[self.external_user.login_key])
        page = self.app.post(url_with_key).follow().follow()
        self.assertContains(page, "Logout")

        page = self.app.get(reverse("django-auth-logout")).follow()
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
        self.assertNotContains(page, "Logout")

    def test_login_key_resend_if_still_valid(self):
        old_key = self.external_user.login_key
        page = self.app.post("/", params={"submit_type": "new_key", "email": self.external_user.email}).follow()
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
        page = self.app.get("/").click("Login")

        # which should then redirect them to OIDC_OP_AUTHORIZTATION_ENDPOINT
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
        self.assertEqual(parse_result.path, "/")

        page = self.app.get(location)
        # A GET here should then redirect to the users real start page.
        # This should be a 403 since the user is external and has no course participation
        page = page.follow(status=403)

        # user should see the Logout button then.
        self.assertIn("Logout", page.body.decode())


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
        page = self.app.get(reverse("django-auth-logout")).follow()
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
