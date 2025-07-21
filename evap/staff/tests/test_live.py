from datetime import date, datetime

from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import (
    element_to_be_clickable,
    invisibility_of_element_located,
    visibility_of_element_located,
)

from evap.evaluation.models import Contribution, Course, Evaluation, Program, Question, Questionnaire, UserProfile
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
            main_language="en",
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
            self.selenium.get(self.reverse("staff:evaluation_edit", args=[evaluation.pk]))

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

    def test_staff_semester_view_columns_not_searchable(self):
        """Regression test for #2461"""

        semester = baker.make("Semester")
        course = baker.make(Course, semester=semester, name_en="course name")
        baker.make(Evaluation, course=course, name_en="evaluation name")

        with self.enter_staff_mode():
            self.selenium.get(self.live_server_url + reverse("staff:semester_view", args=[semester.pk]))

        search_input = self.wait.until(
            visibility_of_element_located((By.CSS_SELECTOR, "input[type='search'][name='search-evaluation']"))
        )
        search_input.clear()
        search_input.send_keys("course name")

        evaluation_table = self.wait.until(visibility_of_element_located((By.ID, "evaluation-table")))
        tds = evaluation_table.find_elements(By.TAG_NAME, "td")
        self.assertTrue(any("course name" in td.text for td in tds))

        search_input.clear()
        search_input.send_keys("exam")

        self.wait.until(invisibility_of_element_located((By.XPATH, "//td[contains(text(),'course name')]")))

        evaluation_table = self.selenium.find_element(By.ID, "evaluation-table")
        tds = evaluation_table.find_elements(By.TAG_NAME, "td")
        self.assertFalse(any("course name" in td.text for td in tds))
