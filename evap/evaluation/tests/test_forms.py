from django.test import TestCase

from model_mommy import mommy

from evap.evaluation.models import UserProfile
from evap.evaluation.forms import NewKeyForm


class TestNewKeyForm(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inactive_external_user = mommy.make(UserProfile, email="inactive@extern.com", is_active=False)

    def test_inactive_external_users_can_not_request_login_key(self):
        data = {
            "submit_type": "new_key",
            "email": "inactive@extern.com"
        }

        form = NewKeyForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn("Inactive users cannot request login keys.", form.errors["email"])

