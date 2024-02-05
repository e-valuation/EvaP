from django.test import TestCase
from model_bakery import baker

from evap.evaluation.forms import NewKeyForm, ProfileForm
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

        form_data = get_form_data_from_instance(ProfileForm, user)
        form_data["delegates"] = [delegate.pk]  # add delegate

        form = ProfileForm(form_data, instance=user)
        self.assertTrue(form.is_valid())
        form.save()

        user = UserProfile.objects.get(email="testuser@institution.example.com")
        self.assertTrue(user.delegates.filter(email="delegate@institution.example.com").exists())


class ProfileFormTests(TestCase):
    def test_name_validation(self):
        user = baker.make(UserProfile)

        form_data = get_form_data_from_instance(ProfileForm, user)

        form_data["first_name_chosen"] = "ĦĕĮĪő Ŵº®lď"
        form = ProfileForm(form_data, instance=user)
        self.assertTrue(form.is_valid())

        form_data["first_name_chosen"] = "Hello \u202eWorld"
        form = ProfileForm(form_data, instance=user)
        self.assertFalse(form.is_valid())


class ResetToNewFormTest(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester, results_are_archived=True)

    def test_reset_to_new(self):
        states = list(Evaluation.State)
        states.remove(Evaluation.State.NEW)
        states.remove(Evaluation.State.PUBLISHED)

        for state in states:  # TODO@Felix: maybe only testing for one state?
            evaluation = baker.make(Evaluation, state=state, course__semester=self.semester)

            semester_overview_page = self.app.get(f"/staff/semester/{self.semester.pk}", user=self.manager, status=200)

            form = semester_overview_page.forms["evaluation_operation_form"]

            form["evaluation"] = [evaluation.pk]

            confirmation_page = form.submit("target_state", value=str(Evaluation.State.NEW.value))

            # TODO: overthink this
            try:
                confirmation_form = confirmation_page.forms["evaluation-operation-form"]
            except KeyError:
                self.assertTrue(False, "WARNING! no confirmation modal was shown!")
                return

            self.assertIn("delete-previous-answers", confirmation_form.fields)

            # TODO@Felix: check if button is checked
            # TODO@Felix: check if checking/unchecking button makes the right stuff

            confirmation_form.submit()

            evaluation = Evaluation.objects.get(pk=evaluation.pk)  # re-get evaluation
            self.assertEqual(evaluation.state, Evaluation.State.NEW, "Did not reset the evaluation")
