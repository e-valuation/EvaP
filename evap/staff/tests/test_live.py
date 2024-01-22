from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

from evap.evaluation.tests.tools import LiveServerTest


class StaffLiveTests(LiveServerTest):
    def test_copy_header(self):
        self._default_login()

        self._enter_staff_mode()

        self.selenium.get(self.live_server_url + reverse("staff:user_import"))

        WebDriverWait(self.selenium, 10).until(
            expected_conditions.visibility_of_element_located((By.CLASS_NAME, "btn-link"))
        )

        # Patch clipboard functions to test functionality
        self.selenium.execute_script("navigator.clipboardExecuted = false;")
        self.selenium.execute_script("navigator.clipboard.writeText = (c) => navigator.clipboardExecuted = c;")

        self.selenium.find_element(By.CLASS_NAME, "btn-link").click()

        copied_text = self.selenium.execute_script("return navigator.clipboardExecuted;")
        self.assertEqual(copied_text, "Title\tFirst name\tLast name\tEmail")
