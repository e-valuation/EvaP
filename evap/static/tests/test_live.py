from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import visibility_of_element_located

from evap.evaluation.tests.tools import LiveServerTest


class NoteBookPlacementLiveTest(LiveServerTest):
    def test_notebook_placement_big_width(self):
        self.selenium.get(self.live_server_url)
        self.selenium.set_window_size(1400, 900)
        self.selenium.find_element(By.ID, "notebookButton").click()

        notebook = self.wait.until(visibility_of_element_located((By.ID, "notebook")))
        width = notebook.value_of_css_property("width")

        self.assertEqual(width, "25vw")

        evap_content = self.selenium.find_element(By.ID, "evapContent")
        margin_top = evap_content.value_of_css_property("margin-top")

        self.assertEqual(margin_top, "0px")

    def test_notebook_placement_large_aspect_ratio(self):
        self.selenium.get(self.live_server_url)
        self.selenium.set_window_size(1399, 932)  # aspect ratio just above 3:2 and width below 1400px
        self.selenium.find_element(By.ID, "notebookButton").click()
        notebook = self.wait.until(visibility_of_element_located((By.ID, "notebook")))
        width = notebook.value_of_css_property("width")

        self.assertEqual(width, "25vw")

        evap_content = self.selenium.find_element(By.ID, "evapContent")
        margin_top = evap_content.value_of_css_property("margin-top")

        self.assertEqual(margin_top, "0px")

    def test_notebook_placement_small_aspect_ratio(self):
        self.selenium.get(self.live_server_url)
        self.selenium.set_window_size(1399, 934)  # aspect ratio just below 3:2 and width below 1400px
        self.selenium.find_element(By.ID, "notebookButton").click()
        notebook = self.wait.until(visibility_of_element_located((By.ID, "notebook")))
        width = notebook.value_of_css_property("width")

        self.assertEqual(width, "80vw")

        evap_content = self.selenium.find_element(By.ID, "evapContent")
        margin_top = evap_content.value_of_css_property("margin-top")

        self.assertEqual(margin_top, "50vh")
