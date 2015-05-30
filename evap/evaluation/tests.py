from django_webtest import WebTest
from django.core import mail
from django.contrib.auth.hashers import make_password
from evap.evaluation.models import UserProfile
from model_mommy import mommy

from datetime import date, timedelta


class LoginTests(WebTest):

    def test_passworduser_login(self):
        """ Tests whether a user can login with an incorrect and a correct password. """
        mommy.make(UserProfile, username='password.user', password=make_password('evap'))
        response = self.app.get("/")
        passwordForm = response.forms[2]
        passwordForm['username'] = 'password.user'
        passwordForm['password'] = 'asd'
        self.assertEqual(passwordForm.submit().status_code, 200)
        passwordForm['password'] = 'evap'
        self.assertEqual(passwordForm.submit().status_code, 302)

    def test_loginkey_login(self):
        """ Tests whether entering a wrong, an expired and a correct login key
            results in the correct return codes. """
        mommy.make(UserProfile, login_key=12345, login_key_valid_until=date.today() + timedelta(1))
        mommy.make(UserProfile, login_key=12346, login_key_valid_until=date.today() - timedelta(1))
        response = self.app.get("/")
        loginkeyForm = response.forms[3]
        loginkeyForm['login_key'] = 1111111
        self.assertEqual(loginkeyForm.submit().status_code, 200)
        loginkeyForm['login_key'] = 12346
        self.assertEqual(loginkeyForm.submit().status_code, 200)
        loginkeyForm['login_key'] = 12345
        self.assertEqual(loginkeyForm.submit().status_code, 302)

    def test_send_new_loginkey(self):
        """ Tests whether requesting a new login key is only possible for existing users,
            shows the expected success message and sends only one email to the requesting
            user without people in cc even if the user has delegates and cc users. """
        mommy.make(UserProfile, email='asdf@example.com')
        response = self.app.get("/")
        emailForm = response.forms[4]
        emailForm['email'] = "doesnotexist@example.com"
        self.assertIn("No user with this email address was found", emailForm.submit())
        email = "asdf@example.com"
        emailForm['email'] = email
        self.assertIn("Successfully sent", emailForm.submit())
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].to == [email])
        self.assertEqual(len(mail.outbox[0].cc), 0)
