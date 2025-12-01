from datetime import date, datetime

from django.urls import reverse
from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import element_to_be_clickable, visibility_of_element_located

from evap.evaluation.models import Contribution, Course, Evaluation, Program, Question, Questionnaire, UserProfile, TextAnswer
from evap.evaluation.tests.tools import LiveServerTest


class EvaluationEditLiveTest(LiveServerTest):
    def test_submit_changes_form_data(self):
        """Regression test for #1769"""

        responsible = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
        )

        general_questionnaire = baker.make(Questionnaire, questions=[baker.make(Question)])
        evaluation.general_contribution.questionnaires.set([general_questionnaire])

        contribution1 = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=responsible,
            order=0,
            role=Contribution.Role.CONTRIBUTOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
        )
        baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=baker.make(UserProfile),
            order=1,
            role=Contribution.Role.EDITOR,
        )

        with self.enter_staff_mode():
            self.selenium.get(self.live_server_url + reverse("staff:evaluation_edit", args=[evaluation.pk]))

        row = self.wait.until(visibility_of_element_located((By.CSS_SELECTOR, "#id_contributions-0-contributor")))
        tomselect_options = row.get_property("tomselect")["options"]
        manager_text = "manager (manager@institution.example.com)"
        manager_options = [key for key, value in tomselect_options.items() if value["text"] == manager_text]
        self.assertEqual(len(manager_options), 1)
        self.selenium.execute_script(
            f"""let tomselect = document.querySelector("#id_contributions-0-contributor").tomselect;
            tomselect.setValue("{manager_options[0]}");"""
        )

        submit_btn = self.wait.until(
            element_to_be_clickable((By.XPATH, "//button[@name='operation' and @value='save']"))
        )

        editor_labels = self.selenium.find_elements(By.XPATH, "//label[contains(text(), 'Editor')]")
        own_and_general_labels = self.selenium.find_elements(By.XPATH, "//label[contains(text(), 'Own and general')]")
        editor_labels[0].click()
        own_and_general_labels[0].click()

        with self.enter_staff_mode():
            submit_btn.click()

        contribution1.refresh_from_db()

        self.assertEqual(contribution1.contributor_id, self.manager.id)
        self.assertEqual(contribution1.order, 0)
        self.assertEqual(contribution1.role, Contribution.Role.EDITOR)
        self.assertEqual(contribution1.textanswer_visibility, Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)

class TextAnswerEditLiveTest(LiveServerTest):
    def test_edit_textanswer_redirect(self):
        """Regression test for #1696"""

        responsible = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
            vote_start_datetime=datetime(2099, 1, 1, 0, 0),
            vote_end_date=date(2099, 12, 31),
            state=Evaluation.State.EVALUATED,
            can_publish_text_results=True
        )

        question1 = baker.make(
            Question,
        )

        general_questionnaire = baker.make(Questionnaire, questions=[question1])
        evaluation.general_contribution.questionnaires.set([general_questionnaire])

        contribution1 = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=None,
            questionnaires=[general_questionnaire]
        )

        textanswer1 = baker.make(
            TextAnswer,
            question=question1,
            contribution=contribution1,
            answer="this is answer will be edited",
            original_answer=None,
            review_decision=TextAnswer.ReviewDecision.UNDECIDED
        )

        textanswer2 = baker.make(
            TextAnswer,
            question=question1,
            contribution=contribution1,
            answer="this is a dummy answer",
            original_answer=None,
            review_decision=TextAnswer.ReviewDecision.UNDECIDED
        )

        with self.enter_staff_mode():
            self.selenium.get(self.live_server_url + reverse("staff:evaluation_textanswer_edit", args=[textanswer1.pk]))

        textanswer_field = self.selenium.find_element(By.XPATH, "//textarea[@name='answer']")
        submit_btn = self.selenium.find_element(By.ID, "textanswer-edit-submit-button")

        textanswer_field.clear()
        textanswer_field.send_keys("edited answer")

        with self.enter_staff_mode():
            submit_btn.click()

        answer = self.selenium.find_elements(By.XPATH, "//div[@class='slider-item card-body active' and @data-layer='2']")

        self.assertEqual(str(answer[0].get_attribute("id")).split('-',1)[1], str(textanswer1.pk))
        