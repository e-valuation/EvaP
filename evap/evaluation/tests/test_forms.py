from django.test import TestCase
from model_bakery import baker

from evap.evaluation.forms import DelegatesForm, NewKeyForm
from evap.evaluation.models import UserProfile
from evap.evaluation.tests.tools import get_form_data_from_instance


class TestNewKeyForm(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inactive_external_user = baker.make(UserProfile, email="inactive@extern.com", is_active=False)

    def test_inactive_external_users_can_not_request_login_key(self):
        data = {"submit_type": "new_key", "email": "inactive@extern.com"}

        form = NewKeyForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn("Inactive users cannot request login keys.", form.errors["email"])


class UserFormTests(TestCase):
    def test_settings_form(self):
        """
        Tests whether the settings form can be submitted without errors
        """
        user = baker.make(UserProfile, email="testuser@institution.example.com")
        delegate = baker.make(UserProfile, email="delegate@institution.example.com")

        self.assertFalse(user.delegates.filter(email="delegate@institution.example.com").exists())

        form_data = get_form_data_from_instance(DelegatesForm, user)
        form_data["delegates"] = [delegate.pk]  # add delegate

        form = DelegatesForm(form_data, instance=user)
        self.assertTrue(form.is_valid())
        form.save()

        user = UserProfile.objects.get(email="testuser@institution.example.com")
        self.assertTrue(user.delegates.filter(email="delegate@institution.example.com").exists())
