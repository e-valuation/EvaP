from django_webtest import WebTest


class ViewTest(WebTest):
    url = "/"
    test_users = []

    def test_check_response_code_200(self):
        for user in self.test_users:
            response = self.app.get(self.url, user=user)
            self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(self.url, user))
