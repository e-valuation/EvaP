from datetime import datetime, date

from django.urls import reverse
from model_bakery import baker

from evap.evaluation.models import UserProfile, Evaluation, Course, Program
from evap.evaluation.tests.tools import LiveServerTest
from selenium.webdriver.support.expected_conditions import element_to_be_clickable, visibility_of_element_located
from selenium.webdriver.common.by import By


class IHaveNoIdeaWhattThisShouldBeCalledLiveTest(LiveServerTest):
    headless = False
    def test_delegation_modal(self):
        responsible = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)],
            responsibles=[responsible]),
            state=Evaluation.State.PREPARED,
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
        )
        self.selenium.get(self.live_server_url + reverse("contributor:index"))

        delegate_button = self.selenium.find_element(By.CSS_SELECTOR, r"confirmation-modal button[data-bs-original-title='Delegate preparation']")
        delegate_button.click()

        open_dropdown_field = self.selenium.find_element(By.CLASS_NAME, "ts-control")
        open_dropdown_field.click()

        first_option = self.selenium.find_element(By.CSS_SELECTOR, r"div[data-value='2']")
        first_option.click()

        submit_button = self.selenium.find_element(By.CSS_SELECTOR, "span[slot='action-text']")
        submit_button.click()

        self.assertEqual(evaluation.num_contributors, 1)
