from django.core import mail
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions

from evap.evaluation.tests.tools import LiveServerTest


class ContactModalTests(LiveServerTest):
    def test_contact_modal(self):
        test_user = self._default_login()

        self.selenium.get(self.live_server_url + reverse("evaluation:index"))
        self.selenium.find_element(By.ID, "feedbackModalShowButton").click()
        self._screenshot("feedback_modal_")

        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "feedbackModalMessageText")))
        self._screenshot("feedback_modal_2")
        self.selenium.find_element(By.ID, "feedbackModalMessageText").send_keys("Testmessage")
        self._screenshot("feedback_modal_typed")
        self.selenium.find_element(By.ID, "feedbackModalActionButton").click()

        self.wait.until(
            expected_conditions.text_to_be_present_in_element(
                (By.CSS_SELECTOR, "#successMessageModal_feedbackModal .modal-body"),
                "Your message was successfully sent.",
            )
        )
        self._screenshot("feedback_modal_success")

        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(mail.outbox[0].subject, f"[EvaP] Message from {test_user.email}")
