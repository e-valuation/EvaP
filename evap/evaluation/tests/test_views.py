from django.contrib.auth.models import Group
from django.core import mail
from django.contrib.auth.hashers import make_password
from django_webtest import WebTest

from evap.evaluation.constants import FEEDBACK_OPEN, FEEDBACK_CLOSED
from evap.evaluation.models import UserProfile, Feedback
from model_mommy import mommy

from datetime import date, timedelta

from evap.evaluation.tests.test_utils import ViewTest


class TestFeedbackCreateView(WebTest):
    csrf_checks = False

    def test_creates(self):
        mommy.make(UserProfile, username='evap')
        self.assertFalse(Feedback.objects.filter(sender_email='unique@mail.de').exists())
        self.app.post('/feedback/create', {'message': 'feedback message', 'sender_email': 'unique@mail.de'}, user='evap')
        self.assertTrue(Feedback.objects.filter(sender_email='unique@mail.de').exists())


class TestFeedbackDeleteView(WebTest):
    def test_deletes(self):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        feedback_obj = mommy.make(Feedback)
        self.assertTrue(Feedback.objects.get(id=feedback_obj.id))

        self.app.get('/feedback/{}/delete'.format(feedback_obj.id), user='staff')

        self.assertFalse(Feedback.objects.filter(id=feedback_obj.id).exists())

    def test_non_staff_cant_delete(self):
        mommy.make(UserProfile, username='non_staff')
        feedback_obj = mommy.make(Feedback)
        self.assertTrue(Feedback.objects.get(id=feedback_obj.id))

        response = self.app.get('/feedback/{}/delete'.format(feedback_obj.id), user='non_staff', expect_errors=True)

        self.assertTrue(Feedback.objects.get(id=feedback_obj.id))
        self.assertEquals(response.status_code, 403)  # FORBIDDEN


class TestFeedbackProcessView(WebTest):
    def test_changes_state(self):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        feedback_obj = mommy.make(Feedback)
        self.assertEqual(Feedback.objects.get(id=feedback_obj.id).state, FEEDBACK_OPEN)

        self.app.get('/feedback/{}/process'.format(feedback_obj.id), user='staff')

        self.assertEqual(Feedback.objects.get(id=feedback_obj.id).state, FEEDBACK_CLOSED)

    def test_non_staff_cant_change_state(self):
        mommy.make(UserProfile, username='non_staff')
        feedback_obj = mommy.make(Feedback)
        self.assertEqual(Feedback.objects.get(id=feedback_obj.id).state, FEEDBACK_OPEN)

        response = self.app.get('/feedback/{}/process'.format(feedback_obj.id), user='non_staff', expect_errors=True)

        self.assertEqual(Feedback.objects.get(id=feedback_obj.id).state, FEEDBACK_OPEN)
        self.assertEquals(response.status_code, 403)  # FORBIDDEN


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

    def test_loginkey_login(self):
        """ Tests whether entering a wrong, an expired and a correct login key
            results in the correct return codes. """
        mommy.make(UserProfile, login_key=12345, login_key_valid_until=date.today() + timedelta(1))
        mommy.make(UserProfile, login_key=12346, login_key_valid_until=date.today() - timedelta(1))
        response = self.app.get("/")
        login_key_form = response.forms[3]
        login_key_form['login_key'] = 1111111
        self.assertEqual(login_key_form.submit().status_code, 200)
        login_key_form['login_key'] = 12346
        self.assertEqual(login_key_form.submit().status_code, 200)
        login_key_form['login_key'] = 12345
        self.assertEqual(login_key_form.submit().status_code, 302)

    def test_send_new_loginkey(self):
        """ Tests whether requesting a new login key is only possible for existing users,
            shows the expected success message and sends only one email to the requesting
            user without people in cc even if the user has delegates and cc users. """
        mommy.make(UserProfile, email='asdf@example.com')
        response = self.app.get("/")
        email_form = response.forms[4]
        email_form['email'] = "doesnotexist@example.com"
        self.assertIn("No user with this email address was found", email_form.submit())
        email = "asdf@example.com"
        email_form['email'] = email
        self.assertIn("Successfully sent", email_form.submit())
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].to == [email])
        self.assertEqual(len(mail.outbox[0].cc), 0)


class TestLegalNoticeView(ViewTest):
    url = '/legal_notice'
    test_users = ['']


class TestFAQView(ViewTest):
    url = '/faq'
    test_users = ['']
