from django.urls import reverse
from django.core import mail

from model_mommy import mommy

from evap.evaluation.models import Contribution, Course, UserProfile
from evap.evaluation.tests.tools import WebTest


class LoginTests(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.external_user = mommy.make(UserProfile, email="extern@extern.com")
        cls.external_user.ensure_valid_login_key()
        cls.inactive_external_user = mommy.make(UserProfile, email="inactive@extern.com", is_active=False)
        cls.inactive_external_user.ensure_valid_login_key()
        course = mommy.make(Course, state='published')
        mommy.make(Contribution, course=course, contributor=cls.external_user, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=course, contributor=cls.inactive_external_user, can_edit=True, responsible=False, comment_visibility=Contribution.ALL_COMMENTS)

    def test_login_url_works(self):
        self.assertRedirects(self.app.get(reverse("contributor:index")), "/?next=/contributor/")

        url_with_key = reverse("contributor:index") + "?loginkey=%s" % self.external_user.login_key
        self.app.get(url_with_key)

    def test_login_key_valid_only_once(self):
        page = self.app.get(reverse("contributor:index") + "?loginkey=%s" % self.external_user.login_key)
        self.assertContains(page, 'Logged in as ' + self.external_user.full_name)
        page = self.app.get(reverse("django-auth-logout")).follow()
        self.assertContains(page, 'Not logged in')
        page = self.app.get(reverse("contributor:index") + "?loginkey=%s" % self.external_user.login_key).follow()
        self.assertContains(page, 'The login URL is not valid anymore.')
        self.assertEqual(len(mail.outbox), 1)  # a new login key was sent
        self.external_user.refresh_from_db()
        page = self.app.get(reverse("contributor:index") + "?loginkey=%s" % self.external_user.login_key)
        self.assertContains(page, 'Logged in as ' + self.external_user.full_name)

    def test_inactive_external_users_can_not_login(self):
        page = self.app.get(reverse("contributor:index") + "?loginkey=%s" % self.inactive_external_user.login_key).follow()
        self.assertContains(page, "Inactive users are not allowed to login")
        self.assertNotContains(page, "Logged in")

    def test_login_key_resend_if_still_valid(self):
        old_key = self.external_user.login_key
        page = self.app.post("/", params={"submit_type": "new_key", "email": self.external_user.email}).follow()
        new_key = UserProfile.objects.get(id=self.external_user.id).login_key

        self.assertEqual(old_key, new_key)
        self.assertEqual(len(mail.outbox), 1)  # a login key was sent
        self.assertContains(page, "We sent you an email with a one-time login URL. Please check your inbox.")

