import time

from django.test import override_settings
from model_bakery import baker
from selenium.webdriver import Keys, ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.expected_conditions import presence_of_element_located, visibility_of_element_located

from evap.evaluation.models import Contribution, Evaluation, Question, Questionnaire, QuestionType, UserProfile
from evap.evaluation.tests.tools import LiveServerTest


class StudentVoteLiveTest(LiveServerTest):
    def setUp(self) -> None:
        super().setUp()
        voting_user1 = baker.make(UserProfile, email="voting_user1@institution.example.com")
        voting_user2 = baker.make(UserProfile, email="voting_user2@institution.example.com")
        contributor1 = baker.make(UserProfile, email="contributor1@institution.example.com")
        contributor2 = baker.make(UserProfile, email="contributor2@institution.example.com")

        evaluation = baker.make(
            Evaluation,
            participants=[voting_user1, voting_user2, contributor1],
            state=Evaluation.State.IN_EVALUATION,
            main_language="en",
        )

        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        bottom_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.BOTTOM)
        contributor_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)

        baker.make(Question, questionnaire=contributor_questionnaire, order=0, type=QuestionType.HEADING)
        baker.make(Question, questionnaire=contributor_questionnaire, order=1, type=QuestionType.TEXT)
        baker.make(Question, questionnaire=contributor_questionnaire, order=2, type=QuestionType.POSITIVE_LIKERT)

        baker.make(Question, questionnaire=top_general_questionnaire, order=0, type=QuestionType.HEADING)
        baker.make(Question, questionnaire=top_general_questionnaire, order=1, type=QuestionType.TEXT)
        baker.make(Question, questionnaire=top_general_questionnaire, order=2, type=QuestionType.POSITIVE_LIKERT)
        baker.make(Question, questionnaire=top_general_questionnaire, order=3, type=QuestionType.GRADE)

        baker.make(Question, questionnaire=bottom_general_questionnaire, order=0, type=QuestionType.HEADING)
        baker.make(Question, questionnaire=bottom_general_questionnaire, order=1, type=QuestionType.TEXT)
        baker.make(Question, questionnaire=bottom_general_questionnaire, order=2, type=QuestionType.POSITIVE_LIKERT)
        baker.make(Question, questionnaire=bottom_general_questionnaire, order=3, type=QuestionType.GRADE)

        baker.make(
            Contribution,
            contributor=contributor1,
            questionnaires=[contributor_questionnaire],
            evaluation=evaluation,
        )
        baker.make(
            Contribution,
            contributor=contributor2,
            questionnaires=[contributor_questionnaire],
            evaluation=evaluation,
        )

        evaluation.general_contribution.questionnaires.set([top_general_questionnaire, bottom_general_questionnaire])
        self.url = self.reverse("student:vote", args=[evaluation.pk])
        self.login(voting_user1)

    def _get_publish_confirmation(self) -> dict[str, WebElement]:
        return {
            "top": self.wait.until(visibility_of_element_located((By.ID, "text_results_publish_confirmation_top"))),
            "bottom": self.selenium.find_element(By.ID, "text_results_publish_confirmation_bottom"),
            "bottom_card": self.selenium.find_element(By.ID, "bottom_text_results_publish_confirmation_card"),
        }

    def test_checking_top_confirm_checkbox_checks_and_hides_bottom(self):
        self.selenium.get(self.url)
        confirmation = self._get_publish_confirmation()

        confirmation["top"].click()

        self.assertTrue(confirmation["bottom"].is_selected())
        self.assertIn("d-none", confirmation["bottom_card"].get_attribute("class"))

    def test_checking_bottom_confirm_checkbox_check_top_but_keeps_bottom_visible(self):
        self.selenium.get(self.url)
        confirmation = self._get_publish_confirmation()

        confirmation["bottom"].click()

        self.assertTrue(confirmation["top"].is_selected())
        self.assertNotIn("d-none", confirmation["bottom_card"].get_attribute("class"))

    def test_resolving_submit_errors_clears_warning(self) -> None:
        self.selenium.get(self.url)
        with self.wait_until_page_reloads():
            self.wait.until(presence_of_element_located((By.ID, "vote-submit-btn"))).click()

        row = self.selenium.find_element(By.CSS_SELECTOR, "#student-vote-form .row:has(.btn-check)")
        checkbox = row.find_element(By.CSS_SELECTOR, "input[type=radio][value='2'] + label.choice-error")
        checkbox.click()
        self.assertEqual(row.find_elements(By.CSS_SELECTOR, ".choice-error"), [])

    @override_settings(SMALL_COURSE_SIZE=2)
    def test_skip_contributor(self) -> None:
        self.selenium.get(self.url)

        button = self.wait.until(presence_of_element_located((By.CSS_SELECTOR, "[data-mark-no-answers-for]")))
        button.click()
        id_ = button.get_attribute("data-mark-no-answers-for")
        vote_area = self.selenium.find_element(By.ID, f"vote-area-{id_}")

        for checkbox in vote_area.find_elements(By.CSS_SELECTOR, "input[type=radio]:not([value='6'])"):
            self.assertFalse(checkbox.is_selected())

        for checkbox in vote_area.find_elements(By.CSS_SELECTOR, "input[type=radio][value='6']"):
            self.assertTrue(checkbox.is_selected())

        self.assertIn(vote_area.get_attribute("class"), ("collapsing", "collapse"))

    @override_settings(SMALL_COURSE_SIZE=2)
    def test_skip_contributor_clears_warning(self) -> None:
        self.selenium.get(self.url)
        button = self.wait.until(presence_of_element_located((By.CSS_SELECTOR, "[data-mark-no-answers-for]")))
        button.click()

        id_ = button.get_attribute("data-mark-no-answers-for")
        self.assertEqual(len(self.selenium.find_elements(By.CSS_SELECTOR, f"#vote-area-{id_} .choice-error")), 0)

    def test_skip_contributor_modal_appears(self) -> None:
        def get_open_modals():
            modals = self.selenium.find_elements(By.CSS_SELECTOR, "confirmation-modal.mark-no-answer-modal")
            return [modal for modal in modals if len(modal.shadow_root.find_elements(By.CSS_SELECTOR, "dialog:open")) == 1]
        def assert_modal_visible_and_close():
            modals = get_open_modals()
            self.assertEqual(len(modals), 1)
            ActionChains(self.selenium).send_keys(Keys.ESCAPE).perform()
        def assert_modal_not_visible():
            modals = get_open_modals()
            self.assertEqual(len(modals), 0)

        self.selenium.get(self.url)

        button = self.wait.until(presence_of_element_located((By.CSS_SELECTOR, "[data-mark-no-answers-for]")))
        id_ = button.get_attribute("data-mark-no-answers-for")
        vote_area = self.selenium.find_element(By.ID, f"vote-area-{id_}")

        textareas = vote_area.find_elements(By.CSS_SELECTOR, "textarea")
        textarea = vote_area.find_element(By.CSS_SELECTOR, f"textarea[name='{textareas[0].get_attribute('name')}']")
        radio_buttons = vote_area.find_elements(By.CSS_SELECTOR, "input[value='1'] + label.vote-btn")
        self.assertEqual(len(radio_buttons), 1)

        open_textanswer = vote_area.find_element(By.CSS_SELECTOR, "button.btn-textanswer")
        open_textanswer.click()

        textarea.click()
        textarea.send_keys("a")
        button.click()
        assert_modal_visible_and_close()

        textarea.click()
        textarea.send_keys(Keys.BACKSPACE)
        radio_buttons[0].click()
        button.click()
        assert_modal_not_visible()
