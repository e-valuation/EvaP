from django.core import mail
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import text_to_be_present_in_element, visibility_of_element_located

from evap.evaluation.tests.tools import LiveServerTest


class ContactModalTests(LiveServerTest):
    def test_contact_modal(self) -> None:
        self.selenium.get(self.live_server_url + reverse("evaluation:index"))
        self.selenium.find_element(By.ID, "feedbackModalShowButton").click()
        self.wait.until(visibility_of_element_located((By.ID, "feedbackModalMessageText")))
        self.selenium.find_element(By.ID, "feedbackModalMessageText").send_keys("Test message")
        self.selenium.find_element(By.ID, "feedbackModalActionButton").click()

        self.wait.until(
            text_to_be_present_in_element(
                (By.CSS_SELECTOR, "#successMessageModal_feedbackModal .modal-body"),
                "Your message was successfully sent.",
            )
        )
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].subject, f"[EvaP] Message from {self.manager.email}")
