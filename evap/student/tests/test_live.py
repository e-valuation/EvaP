from django.test import override_settings
from django.urls import reverse
from model_bakery import baker
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions

from evap.evaluation.models import Contribution, Evaluation, Question, Questionnaire, QuestionType, UserProfile
from evap.evaluation.tests.tools import LiveServerTest


class StudentLiveTests(LiveServerTest):
    def _setup(self):
        # pylint: disable=attribute-defined-outside-init
        self.voting_user1 = baker.make(UserProfile, email="voting_user1@institution.example.com")
        voting_user2 = baker.make(UserProfile, email="voting_user2@institution.example.com")
        contributor1 = baker.make(UserProfile, email="contributor1@institution.example.com")
        contributor2 = baker.make(UserProfile, email="contributor2@institution.example.com")

        # pylint: disable=attribute-defined-outside-init
        self.evaluation = baker.make(
            Evaluation,
            participants=[self.voting_user1, voting_user2, contributor1],
            state=Evaluation.State.IN_EVALUATION,
        )
        # pylint: disable=attribute-defined-outside-init
        self.url = f"/student/vote/{self.evaluation.pk}"

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
            evaluation=self.evaluation,
        )
        baker.make(
            Contribution,
            contributor=contributor2,
            questionnaires=[contributor_questionnaire],
            evaluation=self.evaluation,
        )

        self.evaluation.general_contribution.questionnaires.set(
            [top_general_questionnaire, bottom_general_questionnaire]
        )

    def _get_elements(self):
        self.wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "text_results_publish_confirmation_top"))
        )
        return {
            "top": self.selenium.find_element(By.ID, "text_results_publish_confirmation_top"),
            "bottom": self.selenium.find_element(By.ID, "text_results_publish_confirmation_bottom"),
            "bottom_card": self.selenium.find_element(By.ID, "bottom_text_results_publish_confirmation_card"),
        }

    def test_checking_top_confirm_checkbox_checks_and_hides_bottom(self):
        self._setup()
        self._login(self.voting_user1)

        self.selenium.get(self.live_server_url + reverse("student:vote", args=[self.evaluation.pk]))

        elements = self._get_elements()
        elements["top"].click()

        assert elements["bottom"].is_selected()
        assert "d-none" in elements["bottom_card"].get_attribute("class")

    def test_checking_bottom_confirm_checkbox_check_top_but_keeps_bottom_visible(self):
        self._setup()
        self._login(self.voting_user1)

        self.selenium.get(self.live_server_url + reverse("student:vote", args=[self.evaluation.pk]))

        elements = self._get_elements()
        elements["bottom"].click()

        assert elements["top"].is_selected()
        assert "d-none" not in elements["bottom_card"].get_attribute("class")

    def test_resolving_submit_errors_clears_warning(self):
        self._setup()
        self._login(self.voting_user1)

        self.selenium.get(self.live_server_url + reverse("student:vote", args=[self.evaluation.pk]))
        self.wait.until(expected_conditions.presence_of_element_located((By.ID, "vote-submit-btn"))).click()

        for row in self.selenium.find_elements(By.CSS_SELECTOR, "#student-vote-form .row"):
            try:
                checkbox = row.find_element(By.CSS_SELECTOR, "input[type=radio][value='2'] + label.choice-error")
            except NoSuchElementException:
                continue
            checkbox.click()

            assert len(row.find_elements(By.CSS_SELECTOR, ".choice-error")) == 0

    def test_skip_contributor(self):
        with override_settings(SMALL_COURSE_SIZE=2):
            self._setup()
            self._login(self.voting_user1)

            self.selenium.get(self.live_server_url + reverse("student:vote", args=[self.evaluation.pk]))

            button = self.wait.until(
                expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "[data-mark-no-answers-for]"))
            )
            button.click()
            id_ = button.get_attribute("data-mark-no-answers-for")

            for checkbox in self.selenium.find_elements(
                By.CSS_SELECTOR, f"#vote-area-{id_} input[type=radio]:not([value='6'])"
            ):
                assert not checkbox.is_selected()

            for checkbox in self.selenium.find_elements(
                By.CSS_SELECTOR, f"#vote-area-{id_} input[type=radio][value='6']"
            ):
                assert checkbox.is_selected()

    def test_skip_contributor_clears_warning(self):
        with override_settings(SMALL_COURSE_SIZE=2):
            self._setup()
            self._login(self.voting_user1)

            self.selenium.get(self.live_server_url + reverse("student:vote", args=[self.evaluation.pk]))

            self.wait.until(expected_conditions.presence_of_element_located((By.ID, "vote-submit-btn"))).click()

            button = self.wait.until(
                expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "[data-mark-no-answers-for]"))
            )
            button.click()
            id_ = button.get_attribute("data-mark-no-answers-for")

            assert len(self.selenium.find_elements(By.CSS_SELECTOR, f"#vote-area-{id_} .choice-error")) == 0
