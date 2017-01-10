from django.urls import reverse
from django.core import mail

from model_mommy import mommy

from evap.evaluation.models import UserProfile
from evap.evaluation.tests.tools import WebTest


class LoginTests(WebTest):

    def test_login_key_valid_only_once(self):
        user = mommy.make(UserProfile, email="extern@extern.com")
        user.generate_login_key()
        page = self.app.get(reverse("results:index") + "?loginkey=%s" % user.login_key)
        self.assertContains(page, 'Logged in as ' + user.full_name)
        page = self.app.get(reverse("django-auth-logout")).follow()
        self.assertContains(page, 'Not logged in')
        page = self.app.get(reverse("results:index") + "?loginkey=%s" % user.login_key).follow()
        self.assertContains(page, 'The login URL was already used')
        self.assertEqual(len(mail.outbox), 1)  # a new login key was sent
        user.refresh_from_db()
        page = self.app.get(reverse("results:index") + "?loginkey=%s" % user.login_key)
        self.assertContains(page, 'Logged in as ' + user.full_name)
