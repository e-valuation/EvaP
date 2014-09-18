from django_webtest import WebTest


class LoginTests(WebTest):
    fixtures = ['login_test_data']

    def test_passworduser_login(self):
        response = self.app.get("/")
        passwordForm = response.forms[2]
        passwordForm['username'] = 'password.user'
        passwordForm['password'] = 'asd'
        self.assertEqual(passwordForm.submit().status_code, 200)
        passwordForm['password'] = 'evap'
        self.assertEqual(passwordForm.submit().status_code, 302)

    def test_loginkey_login(self):
        response = self.app.get("/")
        loginkeyForm = response.forms[3]
        loginkeyForm['login_key'] = 1111111
        self.assertEqual(loginkeyForm.submit().status_code, 200)
        loginkeyForm['login_key'] = 12346
        self.assertEqual(loginkeyForm.submit().status_code, 200)
        loginkeyForm['login_key'] = 12345
        self.assertEqual(loginkeyForm.submit().status_code, 302)

    def test_send_new_loginkey(self):
        response = self.app.get("/")
        emailForm = response.forms[4]
        emailForm['email'] = "asdf@example.com"
        self.assertIn("No user with this email address was found", emailForm.submit())
        emailForm['email'] = "expiredloginkey.user@example.com"
        self.assertIn("Successfully sent", emailForm.submit())
