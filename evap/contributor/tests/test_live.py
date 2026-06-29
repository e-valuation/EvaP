from datetime import date, datetime

from model_bakery import baker
from selenium.webdriver.common.by import By

from evap.evaluation.models import Contribution, Course, Evaluation, Program, UserProfile
from evap.evaluation.tests.tools import LiveServerTest, UserProfileSearchLiveServerTest


class ContributorDelegationLiveTest(LiveServerTest):
    def test_delegation_modal(self):
        responsible = baker.make(UserProfile)
        self.login(responsible)

        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            state=Evaluation.State.PREPARED,
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
        )
        self.assertFalse(
            Contribution.objects.filter(
                evaluation=evaluation, contributor__email="manager@institution.example.com"
            ).exists()
        )
        self.assertEqual(evaluation.contributions.count(), 1)
        self.selenium.get(self.reverse("contributor:index"))

        delegate_button = self.selenium.find_element(
            By.CSS_SELECTOR, r"confirmation-modal button[data-bs-original-title='Delegate preparation']"
        )
        delegate_button.click()

        open_dropdown_field = self.selenium.find_element(By.CSS_SELECTOR, "input[placeholder='Please select...']")
        open_dropdown_field.click()

        first_option = self.selenium.find_element(
            By.XPATH, "//div[contains(@class, 'option') and contains(text(), 'manager')]"
        )
        first_option.click()

        submit_button = self.selenium.find_element(By.CSS_SELECTOR, "span[slot='action-text']")
        submit_button.click()

        self.assertEqual(evaluation.contributions.count(), 2)
        self.assertTrue(
            Contribution.objects.filter(
                evaluation=evaluation, contributor__email="manager@institution.example.com"
            ).exists()
        )


class ContributorUserProfileSearchLiveTest(UserProfileSearchLiveServerTest):
    def test_delegation_modal_set_delegate_to(self) -> None:
        """Test delegate_to field in DelegateSelectionForm."""
        possible_delegate = baker.make(
            UserProfile, first_name_given="Jane", last_name="Doe", email="jane.doe@institution.example.com"
        )
        not_active_user = baker.make(
            UserProfile,
            first_name_given="User 1",
            last_name="User 1",
            email="user1@institution.example.com",
            is_active=False,
        )
        is_proxy_user = baker.make(
            UserProfile,
            first_name_given="User 2",
            last_name="User 2",
            email="user2@institution.example.com",
            is_proxy_user=True,
        )

        responsible = baker.make(UserProfile)
        self.login(responsible)

        baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            state=Evaluation.State.PREPARED,
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
        )

        self.selenium.get(self.reverse("contributor:index"))

        delegate_button = self.selenium.find_element(
            By.CSS_SELECTOR, "confirmation-modal button[data-bs-original-title='Delegate preparation']"
        )
        delegate_button.click()

        self.conduct_user_profile_search_test("delegate_to", [possible_delegate], [not_active_user, is_proxy_user])

    def test_evaluation_form_set_participants(self) -> None:
        """Test participants field in EvaluationForm."""
        possible_participant = baker.make(
            UserProfile, first_name_given="Jane", last_name="Doe", email="jane.doe@institution.example.com"
        )
        not_active_user = baker.make(
            UserProfile,
            first_name_given="User 1",
            last_name="User 1",
            email="user1@institution.example.com",
            is_active=False,
        )

        responsible = baker.make(UserProfile)
        self.login(responsible)

        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            state=Evaluation.State.PREPARED,
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
        )

        self.selenium.get(self.reverse("contributor:evaluation_edit", args=[evaluation.pk]))

        self.conduct_user_profile_search_test("participants", [possible_participant], [not_active_user])
