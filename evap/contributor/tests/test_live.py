from datetime import date, datetime

from django.urls import reverse
from model_bakery import baker
from selenium.webdriver.common.by import By

from evap.evaluation.models import Course, Evaluation, Program, UserProfile
from evap.evaluation.tests.tools import LiveServerTest


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
        self.selenium.get(self.live_server_url + reverse("contributor:index"))

        delegate_button = self.selenium.find_element(
            By.CSS_SELECTOR, r"confirmation-modal button[data-bs-original-title='Delegate preparation']"
        )
        delegate_button.click()

        open_dropdown_field = self.selenium.find_element(By.CLASS_NAME, "ts-control")
        open_dropdown_field.click()

        first_option = self.selenium.find_element(By.CSS_SELECTOR, r"div[data-value='2']")
        first_option.click()

        submit_button = self.selenium.find_element(By.CSS_SELECTOR, "span[slot='action-text']")
        submit_button.click()

        self.assertEqual(evaluation.num_contributors, 1)
