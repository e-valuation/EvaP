from datetime import date, datetime

from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import visibility_of

from evap.evaluation.models import Contribution, Course, Evaluation, Program, UserProfile
from evap.evaluation.tests.tools import LiveServerTest, get_open_modals


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

        # Wait for the modal to fully open, so we can click the input that is slotted into the modal
        # (the input is in a slot outside the shadow-dom and exists always, and is always invisible for selenium)
        (modal,) = get_open_modals(self.selenium, *(By.CSS_SELECTOR, "confirmation-modal#delegate-preparation-modal"))
        confirm_button = modal.shadow_root.find_element(By.CSS_SELECTOR, "button[data-event-type='confirm']")
        self.wait.until(visibility_of(confirm_button))

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
