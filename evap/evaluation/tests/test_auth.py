from django.urls import reverse
from django.core import mail
from django.test import override_settings

from model_bakery import baker

from evap.evaluation.models import Contribution, Evaluation, UserProfile
from evap.evaluation.tests.tools import WebTest


class LoginTests(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.external_user = baker.make(UserProfile, email="extern@extern.com")
        cls.external_user.ensure_valid_login_key()
        cls.inactive_external_user = baker.make(UserProfile, email="inactive@extern.com", is_active=False)
        cls.inactive_external_user.ensure_valid_login_key()
        evaluation = baker.make(Evaluation, state='published')
        baker.make(Contribution, evaluation=evaluation, contributor=cls.external_user, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        baker.make(Contribution, evaluation=evaluation, contributor=cls.inactive_external_user, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)

    @override_settings(PAGE_URL='https://example.com')
    def test_login_url_generation(self):
        generated_url = self.external_user.login_url
        self.assertEqual(generated_url, 'https://example.com/key/{}'.format(self.external_user.login_key))

        reversed_url = reverse('evaluation:login_key_authentication', args=[self.external_user.login_key])
        self.assertEqual(reversed_url, '/key/{}'.format(self.external_user.login_key))

    def test_login_url_works(self):
        self.assertRedirects(self.app.get(reverse("contributor:index")), "/?next=/contributor/")

        url_with_key = reverse("evaluation:login_key_authentication", args=[self.external_user.login_key])
        old_login_key = self.external_user.login_key
        old_login_key_valid_until = self.external_user.login_key_valid_until
        page = self.app.get(url_with_key)
        self.external_user.refresh_from_db()
        self.assertEqual(old_login_key, self.external_user.login_key)
        self.assertEqual(old_login_key_valid_until, self.external_user.login_key_valid_until)
        self.assertContains(page, 'Login')
        self.assertContains(page, self.external_user.full_name)

        page = self.app.post(url_with_key).follow().follow()
        self.assertContains(page, 'Logout')
        self.assertContains(page, self.external_user.full_name)

    def test_login_key_valid_only_once(self):
        page = self.app.get(reverse("evaluation:login_key_authentication", args=[self.external_user.login_key]))
        self.assertContains(page, self.external_user.full_name)

        url_with_key = reverse("evaluation:login_key_authentication", args=[self.external_user.login_key])
        page = self.app.post(url_with_key).follow().follow()
        self.assertContains(page, 'Logout')

        page = self.app.get(reverse("django-auth-logout")).follow()
        self.assertNotContains(page, 'Logout')

        page = self.app.get(url_with_key).follow()
        self.assertContains(page, 'The login URL is not valid anymore.')
        self.assertEqual(len(mail.outbox), 1)  # a new login key was sent

        new_key = UserProfile.objects.get(id=self.external_user.id).login_key
        page = self.app.post(reverse("evaluation:login_key_authentication", args=[new_key])).follow().follow()
        self.assertContains(page, self.external_user.full_name)

    def test_inactive_external_users_can_not_login(self):
        page = self.app.get(reverse("evaluation:login_key_authentication", args=[self.inactive_external_user.login_key])).follow()
        self.assertContains(page, "Inactive users are not allowed to login")
        self.assertNotContains(page, "Logout")

    def test_login_key_resend_if_still_valid(self):
        old_key = self.external_user.login_key
        page = self.app.post("/", params={"submit_type": "new_key", "email": self.external_user.email}).follow()
        new_key = UserProfile.objects.get(id=self.external_user.id).login_key

        self.assertEqual(old_key, new_key)
        self.assertEqual(len(mail.outbox), 1)  # a login key was sent
        self.assertContains(page, "We sent you an email with a one-time login URL. Please check your inbox.")
