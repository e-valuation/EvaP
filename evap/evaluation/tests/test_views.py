from django.core import mail
from django.contrib.auth.hashers import make_password

from model_mommy import mommy

from evap.evaluation.models import UserProfile
from evap.evaluation.tests.tools import ViewTest


class TestIndexView(ViewTest):
    url = '/'
    test_users = ['']

    def test_passworduser_login(self):
        """ Tests whether a user can login with an incorrect and a correct password. """
        mommy.make(UserProfile, username='password.user', password=make_password('evap'))
        response = self.app.get("/")
        password_form = response.forms[2]
        password_form['username'] = 'password.user'
        password_form['password'] = 'asd'
        self.assertEqual(password_form.submit().status_code, 200)
        password_form['password'] = 'evap'
        self.assertEqual(password_form.submit().status_code, 302)

    def test_send_new_loginkey(self):
        """ Tests whether requesting a new login key is only possible for existing users,
            shows the expected success message and sends only one email to the requesting
            user without people in cc even if the user has delegates and cc users. """
        mommy.make(UserProfile, email='asdf@example.com')
        response = self.app.get("/")
        email_form = response.forms[3]
        email_form['email'] = "doesnotexist@example.com"
        self.assertIn("No user with this email address was found", email_form.submit())
        email = "asdf@example.com"
        email_form['email'] = email
        self.assertIn("We sent you", email_form.submit().follow())
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].to == [email])
        self.assertEqual(len(mail.outbox[0].cc), 0)


class TestLegalNoticeView(ViewTest):
    url = '/legal_notice'
    test_users = ['']


class TestFAQView(ViewTest):
    url = '/faq'
    test_users = ['']


class TestSendFeedbackView(ViewTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='evap')

    def test_sends_mail(self):
        self.app.post('/feedback/send', params={'message': 'feedback message', 'sender_email': 'unique@mail.de'}, user='evap')
        self.assertEqual(len(mail.outbox), 1)


class TestChangeLanguageView(ViewTest):
    url = '/set_lang'
    csrf_checks = False

    def test_changes_language(self):
        user = mommy.make(UserProfile, username='tester', language='de')

        self.app.post(self.url, params={'language': 'en'}, user='tester')

        user.refresh_from_db()
        self.assertEqual(user.language, 'en')
